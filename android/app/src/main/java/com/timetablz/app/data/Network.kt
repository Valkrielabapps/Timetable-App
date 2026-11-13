package com.timetablz.app.data

import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit

/** A failed request, with the message the server gave ("Incorrect email or password"). status 0 = no connection. */
class ApiException(val status: Int, message: String) : Exception(message) {
    val offline get() = status == 0
}

/** The signed-in person's token, read by every request. */
class TokenHolder {
    @Volatile var token: String? = null
}

object Network {
    const val BASE_URL = "https://timetablz.com/api/"

    val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    /**
     * One client for the whole app. Every request carries the token; a 401 on
     * a signed-in request (the session ended or was revoked) calls
     * [onUnauthorized] once, wherever it happened - the one place the app
     * signs itself out.
     */
    fun api(tokens: TokenHolder, onUnauthorized: () -> Unit): TimetablzApi {
        val client = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val token = tokens.token
                val request = chain.request().newBuilder()
                    .header("Accept", "application/json")
                    .apply { if (token != null) header("Authorization", "Bearer $token") }
                    .build()
                val response = chain.proceed(request)
                if (response.code == 401 && token != null && !request.url.encodedPath.contains("/auth/")) onUnauthorized()
                response
            }
            .build()
        return Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(TimetablzApi::class.java)
    }
}

/** Runs one request, turning every way it can fail into an [ApiException] with a message fit to show. */
suspend fun <T> apiCall(block: suspend () -> T): T = try {
    block()
} catch (e: HttpException) {
    throw ApiException(e.code(), errorMessage(e.code(), e.response()?.errorBody()?.string()))
} catch (e: IOException) {
    throw ApiException(0, "Couldn't reach Timetablz. Check your internet connection.")
} catch (e: SerializationException) {
    throw ApiException(-1, "Timetablz sent back something unexpected. Update the app, or try again.")
}

private fun errorMessage(code: Int, body: String?): String {
    val detail = runCatching { Network.json.parseToJsonElement(body ?: "").jsonObject["detail"] }.getOrNull()
    return when {
        detail is JsonPrimitive && detail.isString -> detail.content
        detail is JsonArray && detail.isNotEmpty() ->
            (detail[0] as? JsonObject)?.get("msg")?.jsonPrimitive?.content ?: "Something went wrong."
        code == 401 -> "Please sign in again."
        code == 403 -> "Your account can't do that for this school."
        code == 429 -> "Too many tries. Wait a few minutes and try again."
        else -> "Something went wrong ($code). Try again."
    }
}
