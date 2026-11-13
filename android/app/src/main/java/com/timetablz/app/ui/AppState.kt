package com.timetablz.app.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.timetablz.app.data.Api
import com.timetablz.app.data.ApiException
import com.timetablz.app.data.Period
import com.timetablz.app.data.School
import com.timetablz.app.data.Session
import com.timetablz.app.data.Teacher
import com.timetablz.app.data.Timetable
import com.timetablz.app.data.User

/** Everything one school's screens read, loaded together. */
data class SchoolData(val periods: List<Period>, val teachers: List<Teacher>, val timetable: Timetable?)

/**
 * The signed-in person, their schools and the chosen school's data. One
 * object the screens share; Compose redraws whatever reads a value when it
 * changes.
 */
class AppState(private val session: Session) {
    val api = Api(token = session.token)

    var user by mutableStateOf<User?>(null)
    var schools by mutableStateOf<List<School>>(emptyList())
    var school by mutableStateOf<School?>(null)
    var data by mutableStateOf<SchoolData?>(null)
    var loading by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    /** True until the first check of a saved sign-in has finished. */
    var starting by mutableStateOf(session.token != null)

    val signedIn get() = user != null

    var timetableView: String
        get() = session.timetableView
        set(v) { session.timetableView = v }

    /** On launch: a saved sign-in still good? Then straight back in. */
    suspend fun resume() {
        if (session.token == null) { starting = false; return }
        try {
            user = api.me()
            afterSignIn()
        } catch (e: ApiException) {
            if (e.status == 401) signOut() else error = e.message
        } finally {
            starting = false
        }
    }

    suspend fun signIn(email: String, password: String) {
        val (token, u) = api.login(email.trim(), password)
        api.token = token
        session.token = token
        user = u
        afterSignIn()
    }

    suspend fun acceptTerms() {
        user = api.acceptTerms(user?.termsVersion ?: "")
    }

    private suspend fun afterSignIn() {
        schools = api.schools()
        val saved = schools.firstOrNull { it.id == session.schoolId }
        if (saved != null) pick(saved) else if (schools.size == 1) pick(schools.first())
    }

    suspend fun pick(s: School) {
        school = s
        session.schoolId = s.id
        reload()
    }

    suspend fun reload() {
        val s = school ?: return
        loading = true
        error = null
        try {
            data = SchoolData(api.periods(s.id), api.teachers(s.id), api.currentTimetable(s.id))
        } catch (e: ApiException) {
            if (e.status == 401) signOut() else error = e.message
        } finally {
            loading = false
        }
    }

    fun switchSchool() {
        school = null
        data = null
        session.schoolId = null
    }

    fun signOut() {
        session.signOut()
        api.token = null
        user = null
        schools = emptyList()
        school = null
        data = null
    }
}
