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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/** Everything one school's screens read, loaded together. */
data class SchoolData(val periods: List<Period>, val teachers: List<Teacher>, val timetable: Timetable?)

/**
 * The signed-in person, their schools and the chosen school's data. One
 * object the screens share; Compose redraws whatever reads a value when it
 * changes.
 */
class AppState(private val session: Session) {
    val api = Api(token = session.token)

    /**
     * Work that changes which screen is showing (signing in, loading schools,
     * picking one) runs here, not in a screen's own scope: a screen's scope is
     * cancelled the moment the app moves off it, which used to cut the school
     * list off half-loaded.
     */
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

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

    /** Settings → Theme: "system", "light" or "dark". */
    var theme by mutableStateOf(session.theme)
        private set

    fun chooseTheme(t: String) {
        theme = t
        session.theme = t
    }

    var notifyCover by mutableStateOf(session.notifyCover)
        private set

    fun setNotify(on: Boolean) {
        notifyCover = on
        session.notifyCover = on
    }

    /** The teacher chosen in Settings → "I am", for this school. */
    var chosenMe by mutableStateOf<Int?>(null)
        private set

    fun chooseMe(teacherId: Int?) {
        val s = school ?: return
        chosenMe = teacherId
        session.setMyTeacherId(s.id, teacherId)
    }

    /** Which teacher the signed-in person is here: chosen, else matched by email. */
    fun me(): com.timetablz.app.data.Teacher? =
        com.timetablz.app.data.MyCover.whoAmI(data?.teachers ?: emptyList(), user?.email, chosenMe)

    /** On launch: a saved sign-in still good? Then straight back in. */
    suspend fun resume() {
        if (session.token == null) { starting = false; return }
        try {
            user = api.me()
            session.userEmail = user?.email
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
        session.userEmail = u.email
        afterSignIn()
    }

    suspend fun signInWithGoogle(idToken: String) {
        val (token, u) = api.google(idToken)
        api.token = token
        session.token = token
        user = u
        session.userEmail = u.email
        afterSignIn()
    }

    suspend fun acceptTerms() {
        user = api.acceptTerms(user?.termsVersion ?: "")
        if (schools.isEmpty()) loadSchools()
    }

    /** True once the school list has been fetched without an error. */
    var schoolsLoaded by mutableStateOf(false)

    private suspend fun afterSignIn() = loadSchools()

    /**
     * The schools this account owns or belongs to. A failure is kept in
     * [error] for the school screen to show with Try again - never shown as
     * "no schools", which it isn't.
     */
    suspend fun loadSchools() {
        loading = true
        error = null
        try {
            schools = api.schools()
            schoolsLoaded = true
            val saved = schools.firstOrNull { it.id == session.schoolId }
            if (saved != null) pick(saved) else if (schools.size == 1) pick(schools.first())
        } catch (e: ApiException) {
            schoolsLoaded = false
            if (e.status == 401) signOut() else error = "Couldn't load your schools: ${e.message}"
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            schoolsLoaded = false
            error = "Couldn't load your schools (${e.javaClass.simpleName}: ${e.message})."
        } finally {
            loading = false
        }
    }

    suspend fun pick(s: School) {
        school = s
        session.schoolId = s.id
        chosenMe = session.myTeacherId(s.id)
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
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = "Couldn't read the school's data (${e.javaClass.simpleName}: ${e.message})."
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
        schoolsLoaded = false
        school = null
        data = null
    }
}
