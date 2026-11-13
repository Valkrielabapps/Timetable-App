package com.timetablz.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.timetablz.app.data.AppContainer
import com.timetablz.app.data.ApiException
import com.timetablz.app.data.MyCover
import com.timetablz.app.data.SchoolData
import com.timetablz.app.data.School
import com.timetablz.app.data.Settings
import com.timetablz.app.data.Teacher
import com.timetablz.app.data.User
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Who's signed in, their schools, the chosen school - what every screen shares. */
data class SessionUi(
    val starting: Boolean = true,
    val user: User? = null,
    val schools: List<School> = emptyList(),
    val schoolsLoaded: Boolean = false,
    val school: School? = null,
    val loading: Boolean = false,
    /** Refreshing the school's data in the background. */
    val refreshing: Boolean = false,
    /** Showing the saved copy because Timetablz can't be reached. */
    val offline: Boolean = false,
    val error: String? = null,
    val authBusy: String? = null,
    val authError: String? = null,
)

/**
 * The app-wide ViewModel (one per activity): signing in and out, the terms,
 * picking a school, and the school's data - from the offline copy at once,
 * then refreshed. Everything runs in viewModelScope, so leaving a screen
 * never cuts it off half-way.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SessionViewModel(private val c: AppContainer) : ViewModel() {
    private val _ui = MutableStateFlow(SessionUi())
    val ui: StateFlow<SessionUi> = _ui.asStateFlow()

    val settings: StateFlow<Settings> = c.store.settings.stateIn(viewModelScope, SharingStarted.Eagerly, Settings())

    /** The chosen school's periods, teachers and timetable, from the offline copy (kept fresh by [refresh]). */
    val schoolData: StateFlow<SchoolData?> = _ui.map { it.school?.id }.distinctUntilChanged()
        .flatMapLatest { id -> if (id == null) flowOf(null) else c.schools.data(id) }
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    init {
        viewModelScope.launch { c.signedOut.collect { signOut() } }
        resume()
    }

    /** Which teacher the signed-in person is here: chosen in Settings, else matched by email. */
    fun me(data: SchoolData?, settings: Settings, ui: SessionUi): Teacher? =
        MyCover.whoAmI(data?.teachers ?: emptyList(), ui.user?.email, ui.school?.id?.let { settings.me[it] })

    private fun resume() = viewModelScope.launch {
        if (!c.auth.restore()) {
            _ui.update { it.copy(starting = false) }
            return@launch
        }
        try {
            val user = c.auth.me()
            _ui.update { it.copy(user = user) }
            loadSchools(user)
        } catch (e: ApiException) {
            if (e.offline) openOffline() else if (e.status == 401) signOut() else _ui.update { it.copy(error = e.message) }
        } finally {
            _ui.update { it.copy(starting = false) }
        }
    }

    /** No signal: open on the account and school as last seen. */
    private suspend fun openOffline() {
        val account = c.auth.cachedAccount() ?: run {
            _ui.update { it.copy(error = "Couldn't reach Timetablz. Check your internet connection.") }
            return
        }
        val saved = account.schools.firstOrNull { it.id == settings.value.schoolId || it.id == c.store.current().schoolId }
        _ui.update {
            it.copy(user = account.user, schools = account.schools, schoolsLoaded = true, school = saved, offline = true)
        }
    }

    fun signIn(email: String, password: String) = auth("email") { c.auth.login(email, password) }

    fun signInWithGoogle(idToken: String) = auth("google") { c.auth.google(idToken) }

    private fun auth(kind: String, block: suspend () -> User) = viewModelScope.launch {
        _ui.update { it.copy(authBusy = kind, authError = null) }
        try {
            val user = block()
            _ui.update { it.copy(user = user, authBusy = null) }
            loadSchools(user)
        } catch (e: ApiException) {
            _ui.update { it.copy(authBusy = null, authError = e.message) }
        }
    }

    fun showAuthError(message: String?) = _ui.update { it.copy(authError = message) }

    fun acceptTerms() = viewModelScope.launch {
        val user = _ui.value.user ?: return@launch
        _ui.update { it.copy(authBusy = "terms", authError = null) }
        try {
            val updated = c.auth.acceptTerms(user.termsVersion)
            _ui.update { it.copy(user = updated, authBusy = null) }
            if (!_ui.value.schoolsLoaded) loadSchools(updated)
        } catch (e: ApiException) {
            _ui.update { it.copy(authBusy = null, authError = e.message) }
        }
    }

    fun retrySchools() = viewModelScope.launch { _ui.value.user?.let { loadSchools(it) } }

    private suspend fun loadSchools(user: User) {
        _ui.update { it.copy(loading = true, error = null) }
        try {
            val schools = c.auth.schools(user)
            val savedId = c.store.current().schoolId
            val pick = schools.firstOrNull { it.id == savedId } ?: schools.singleOrNull()
            _ui.update { it.copy(schools = schools, schoolsLoaded = true, loading = false, offline = false) }
            if (pick != null) choose(pick)
        } catch (e: CancellationException) {
            throw e
        } catch (e: ApiException) {
            _ui.update { it.copy(loading = false, schoolsLoaded = false, error = "Couldn't load your schools: ${e.message}") }
        }
    }

    fun pick(school: School) = viewModelScope.launch { choose(school) }

    private suspend fun choose(school: School) {
        _ui.update { it.copy(school = school) }
        c.store.setSchool(school.id)
        refreshNow()
    }

    /** Fetch the school's latest data and cover into the offline copy; screens update by themselves. */
    fun refresh() = viewModelScope.launch { refreshNow() }

    private suspend fun refreshNow() {
        val id = _ui.value.school?.id ?: return
        _ui.update { it.copy(refreshing = true, error = null) }
        try {
            c.schools.refresh(id)
            c.cover.refresh(id)
            _ui.update { it.copy(refreshing = false, offline = false) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: ApiException) {
            _ui.update {
                if (e.offline) it.copy(refreshing = false, offline = true)
                else it.copy(refreshing = false, error = e.message)
            }
        }
    }

    fun switchSchool() = viewModelScope.launch {
        c.store.setSchool(null)
        _ui.update { it.copy(school = null) }
    }

    fun signOut() = viewModelScope.launch {
        c.auth.signOut()
        _ui.value = SessionUi(starting = false)
    }

    // ---- settings
    fun chooseTheme(theme: String) = viewModelScope.launch { c.store.setTheme(theme) }
    fun setNotify(on: Boolean) = viewModelScope.launch { c.store.setNotify(on) }
    fun introSeen() = viewModelScope.launch { c.store.setIntroSeen() }
    fun chooseMe(teacherId: Int?) = viewModelScope.launch {
        val s = _ui.value.school ?: return@launch
        c.store.setMe(s.id, teacherId)
    }
}
