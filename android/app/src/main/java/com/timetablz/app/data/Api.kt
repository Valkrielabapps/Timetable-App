package com.timetablz.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** A failed request, with the message the server gave ("Incorrect email or password"). */
class ApiException(val status: Int, message: String) : Exception(message)

/**
 * The Timetablz API - the same backend and accounts as timetablz.com.
 * Plain HttpURLConnection, run off the main thread.
 */
class Api(private val base: String = BASE_URL, var token: String? = null) {

    companion object {
        const val BASE_URL = "https://timetablz.com/api"
    }

    // ------------------------------------------------------------ account

    suspend fun login(email: String, password: String): Pair<String, User> {
        val o = JSONObject(request("POST", "/auth/login", JSONObject().put("email", email).put("password", password)))
        return o.getString("access_token") to parseUser(o.getJSONObject("user"))
    }

    /** [idToken] from Google's account chooser - see GoogleSignIn. */
    suspend fun google(idToken: String): Pair<String, User> {
        val o = JSONObject(request("POST", "/auth/google", JSONObject().put("credential", idToken)))
        return o.getString("access_token") to parseUser(o.getJSONObject("user"))
    }

    suspend fun me(): User = parseUser(JSONObject(request("GET", "/auth/me")))

    suspend fun acceptTerms(version: String): User =
        parseUser(JSONObject(request("POST", "/auth/accept-terms", JSONObject().put("version", version))))

    suspend fun schools(): List<School> = parseSchools(JSONArray(request("GET", "/schools")))

    // ------------------------------------------------------------ the school's data

    suspend fun periods(schoolId: Int) = parsePeriods(JSONArray(request("GET", "/periods?school_id=$schoolId")))

    suspend fun teachers(schoolId: Int) = parseTeachers(JSONArray(request("GET", "/teachers?school_id=$schoolId")))

    /** The version the school works from - the one the website's Timetable tab shows. */
    suspend fun currentTimetable(schoolId: Int): Timetable? {
        val all = parseTimetables(JSONArray(request("GET", "/timetables?school_id=$schoolId")))
        val pick = all.firstOrNull { it.isCurrent } ?: all.filter { it.status == "draft" }.maxByOrNull { it.id } ?: return null
        return parseTimetable(JSONObject(request("GET", "/timetables/${pick.id}")))
    }

    // ------------------------------------------------------------ cover

    suspend fun covers(schoolId: Int) = parseCovers(JSONArray(request("GET", "/schools/$schoolId/substitutions")))

    suspend fun saveCover(schoolId: Int, body: JSONObject) {
        request("POST", "/schools/$schoolId/substitutions", body)
    }

    suspend fun summary(schoolId: Int, date: String): Summary =
        parseSummary(JSONObject(request("GET", "/schools/$schoolId/substitutions/summary?date=${enc(date)}")))

    /** Email each covering teacher their cover, with calendar invites. */
    suspend fun notify(schoolId: Int, date: String, everyone: Boolean): NotifyResult =
        parseNotify(JSONObject(request("POST", "/schools/$schoolId/substitutions/notify",
            JSONObject().put("date", date).put("everyone", everyone))))

    // ------------------------------------------------------------ plumbing

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

    private suspend fun request(method: String, path: String, body: JSONObject? = null): String = withContext(Dispatchers.IO) {
        val conn = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 15_000
            readTimeout = 30_000
            setRequestProperty("Accept", "application/json")
            token?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            if (code !in 200..299) throw ApiException(code, errorMessage(code, text))
            text
        } catch (e: IOException) {
            // Some Android versions throw on a 401 that carries no challenge header.
            if (e.message?.contains("authentication challenge", ignoreCase = true) == true) {
                throw ApiException(401, if (path == "/auth/login") "Incorrect email or password" else "Please sign in again.")
            }
            throw ApiException(0, "Couldn't reach Timetablz. Check your internet connection and try again.")
        } finally {
            conn.disconnect()
        }
    }

    private fun errorMessage(code: Int, text: String): String {
        val detail = runCatching { JSONObject(text).opt("detail") }.getOrNull()
        return when {
            detail is String -> detail
            detail is JSONArray && detail.length() > 0 -> detail.getJSONObject(0).optString("msg", "Something went wrong.")
            code == 401 -> "Please sign in again."
            code == 403 -> "Your account can't do that for this school."
            code == 429 -> "Too many tries. Wait a few minutes and try again."
            else -> "Something went wrong ($code). Try again."
        }
    }
}
