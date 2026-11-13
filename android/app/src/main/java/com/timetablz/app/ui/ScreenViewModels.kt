package com.timetablz.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.timetablz.app.data.AppContainer
import com.timetablz.app.data.ApiException
import com.timetablz.app.data.Cover
import com.timetablz.app.data.Dates
import com.timetablz.app.data.Lesson
import com.timetablz.app.data.Ranked
import com.timetablz.app.data.SavedCover
import com.timetablz.app.data.SchoolData
import com.timetablz.app.data.Summary
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

// ---------------------------------------------------------------- timetables

/** Which day and which section or teacher a timetable page shows. One per page, kept across rotation. */
class TimetableViewModel : ViewModel() {
    val day = MutableStateFlow<Int?>(null)
    val sectionId = MutableStateFlow<Int?>(null)
    val teacherId = MutableStateFlow<Int?>(null)
}

// ---------------------------------------------------------- make substitutions

data class CoverUi(
    val date: String = Dates.today(),
    val absent: Set<Int> = emptySet(),
    /** lesson key -> substitute id (null = left uncovered). */
    val picks: Map<String, Int?> = emptyMap(),
    val busy: String? = null,
    val note: String? = null,
    val error: String? = null,
    val summary: Summary? = null,
    val savedToday: Boolean = false,
)

/**
 * A day's cover being arranged. Starts from what's saved for the day; marking
 * someone away fills each of their lessons with the best free teacher
 * (Cover.autofill - the website's rules); Save and Email go to the server.
 * Unsaved changes survive rotation and a background refresh.
 */
class CoverViewModel(private val c: AppContainer) : ViewModel() {
    private val _ui = MutableStateFlow(CoverUi())
    val ui: StateFlow<CoverUi> = _ui.asStateFlow()

    private var schoolId: Int? = null
    private var isAdmin = false
    private var data: SchoolData? = null
    private var saved: List<SavedCover> = emptyList()
    private var dirty = false
    private var watching: Job? = null

    fun bind(schoolId: Int, isAdmin: Boolean, data: SchoolData) {
        this.data = data
        this.isAdmin = isAdmin
        if (this.schoolId != schoolId) {
            this.schoolId = schoolId
            dirty = false
            watching?.cancel()
            watching = viewModelScope.launch {
                c.cover.covers(schoolId).collect { list ->
                    saved = list ?: emptyList()
                    if (!dirty) loadDay()
                }
            }
        }
    }

    private val entries get() = data?.timetable?.entries ?: emptyList()
    private val load get() = Cover.weeklyLoad(entries)

    fun dayLessons(): List<Lesson> = Cover.lessonsOn(entries, Dates.weekday(_ui.value.date))
    fun toCover(): List<Lesson> = dayLessons().filter { it.teacherId in _ui.value.absent }
    fun weeklyLoad(): Map<Int, Int> = load

    fun rank(lesson: Lesson): Ranked =
        Cover.rank(lesson, data?.teachers ?: emptyList(), entries, _ui.value.absent, _ui.value.picks, toCover(), load)

    fun setDate(date: String) {
        dirty = false
        _ui.update { it.copy(date = date, note = null, error = null) }
        loadDay()
    }

    fun setAbsent(ids: Set<Int>) {
        dirty = true
        _ui.update { it.copy(absent = ids, note = null) }
        autofill()
    }

    fun pick(lessonKey: String, teacherId: Int?) {
        dirty = true
        _ui.update { it.copy(picks = it.picks + (lessonKey to teacherId), note = null) }
    }

    private fun loadDay() {
        val date = _ui.value.date
        val here = saved.firstOrNull { it.date == date && it.category == null }
        val absent = here?.absentIds?.ifEmpty { here.changes.map { it.absentTeacherId }.toSet() } ?: emptySet()
        _ui.update {
            it.copy(
                absent = absent,
                picks = if (here != null) Cover.picksFrom(here, dayLessons()) else emptyMap(),
                savedToday = here != null,
                summary = if (here == null) null else it.summary,
            )
        }
        autofill()
        if (here != null || !isAdmin) loadSummary()
    }

    private fun autofill() {
        val d = data ?: return
        _ui.update { it.copy(picks = Cover.autofill(toCover(), d.teachers, entries, it.absent, it.picks, load)) }
    }

    private fun loadSummary() {
        val id = schoolId ?: return
        val date = _ui.value.date
        viewModelScope.launch {
            val s = runCatching { c.cover.summary(id, date) }.getOrNull()
            if (_ui.value.date == date) _ui.update { it.copy(summary = s) }
        }
    }

    fun save() {
        val id = schoolId ?: return
        val u = _ui.value
        viewModelScope.launch {
            _ui.update { it.copy(busy = "save", error = null, note = null) }
            try {
                c.cover.save(id, Cover.body(u.date, u.absent, toCover(), u.picks))
                dirty = false
                _ui.update { it.copy(busy = null, savedToday = true, note = "Saved. Teachers can see it on the website and in the app.") }
                loadSummary()
            } catch (e: ApiException) {
                _ui.update { it.copy(busy = null, error = e.message) }
            }
        }
    }

    fun email() {
        val id = schoolId ?: return
        val date = _ui.value.date
        viewModelScope.launch {
            _ui.update { it.copy(busy = "email", error = null) }
            try {
                val r = c.cover.notify(id, date)
                val note = when {
                    !r.configured -> "Email isn't set up for Timetablz yet."
                    r.sent.isEmpty() && r.noEmail.isEmpty() && r.failed.isEmpty() -> "Nobody needed an email."
                    else -> buildString {
                        if (r.sent.isNotEmpty()) append("Emailed ${r.sent.joinToString(", ")}. ")
                        if (r.noEmail.isNotEmpty()) append("No email address for ${r.noEmail.joinToString(", ")}. ")
                        if (r.failed.isNotEmpty()) append("Couldn't send to ${r.failed.joinToString(", ")}${r.reason?.let { ": $it" } ?: ""}.")
                    }.trim()
                }
                _ui.update { it.copy(busy = null, note = note) }
            } catch (e: ApiException) {
                _ui.update { it.copy(busy = null, error = e.message) }
            }
        }
    }
}

// ----------------------------------------------------------- my substitutions

/** The school's saved cover from the offline copy, refreshed on open. */
@OptIn(ExperimentalCoroutinesApi::class)
class MySubstitutionsViewModel(private val c: AppContainer) : ViewModel() {
    private val school = MutableStateFlow<Int?>(null)
    val error = MutableStateFlow<String?>(null)

    val covers: StateFlow<List<SavedCover>?> = school
        .flatMapLatest { id -> if (id == null) flowOf(null) else c.cover.covers(id) }
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    fun bind(schoolId: Int) {
        if (school.value == schoolId) return
        school.value = schoolId
        viewModelScope.launch {
            error.value = try {
                c.cover.refresh(schoolId)
                null
            } catch (e: ApiException) {
                if (e.offline) "Offline: showing the last saved copy." else e.message
            }
        }
    }
}
