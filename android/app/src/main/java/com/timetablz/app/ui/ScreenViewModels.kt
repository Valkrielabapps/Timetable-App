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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.withContext
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
    /** My timetable: the whole week in one frame instead of one day. */
    val week = MutableStateFlow(false)
}

// ---------------------------------------------------------- make substitutions

data class CoverUi(
    val date: String = Dates.today(),
    /** The part of the school being arranged (Cover.WHOLE or a part key); null until chosen. */
    val part: String? = null,
    /** Teacher -> null (away all day) or the periods they're away. */
    val absences: Map<Int, Set<Int>?> = emptyMap(),
    /** lesson key -> substitute id (null = left uncovered). */
    val picks: Map<String, Int?> = emptyMap(),
    val busy: String? = null,
    val note: String? = null,
    val error: String? = null,
    val summary: Summary? = null,
    val savedToday: Boolean = false,
)

/**
 * A day's cover being arranged, in the website's steps: date, part of the
 * school, who's away (all day or some periods), then a substitute for each
 * lesson (Cover.rank - the website's three groups). Starts from what's saved
 * for that date and part; Save, Email and the summary go to the server for
 * that part. Unsaved changes survive rotation and a background refresh.
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
        val changed = this.data !== data
        this.data = data
        this.isAdmin = isAdmin
        if (this.schoolId != schoolId) {
            this.schoolId = schoolId
            dirty = false
            watching?.cancel()
            watching = viewModelScope.launch {
                // The part chosen last time for this school, as the website remembers it.
                val part = c.store.coverPart(schoolId)
                _ui.update { it.copy(part = part, absences = emptyMap(), picks = emptyMap(), summary = null) }
                c.cover.covers(schoolId).collect { list ->
                    saved = list ?: emptyList()
                    if (!dirty) loadDay()
                }
            }
        } else if (changed && !dirty) {
            loadDay()
        }
    }

    private val entries get() = data?.timetable?.entries ?: emptyList()

    private var derivedFor: SchoolData? = null
    private var _load: Map<Int, Int> = emptyMap()
    private var _partOf: Map<Int, String?> = emptyMap()
    private var _teacherParts: Map<Int, Set<String?>> = emptyMap()
    private fun derive() {
        if (derivedFor === data) return
        derivedFor = data
        _load = Cover.weeklyLoad(entries)
        _partOf = data?.partOfSection() ?: emptyMap()
        _teacherParts = Cover.partsOfTeachers(entries, _partOf)
    }
    private val load get() = derive().let { _load }
    private val partOf get() = derive().let { _partOf }
    private val teacherParts get() = derive().let { _teacherParts }

    private fun lessonsFor(u: CoverUi): List<Lesson> =
        u.part?.let { Cover.lessonsOn(entries, Dates.weekday(u.date), it, partOf) } ?: emptyList()
    private fun coverFor(u: CoverUi, lessons: List<Lesson> = lessonsFor(u)) =
        lessons.filter { Cover.isAway(u.absences, it.teacherId, it.periodId) }
    private fun elsewhereFor(u: CoverUi) = Cover.elsewhere(saved, u.date, u.part ?: Cover.WHOLE)

    fun dayLessons(): List<Lesson> = lessonsFor(_ui.value)
    fun toCover(): List<Lesson> = coverFor(_ui.value)
    fun weeklyLoad(): Map<Int, Int> = load

    fun rank(lesson: Lesson): Ranked {
        val u = _ui.value
        return Cover.rank(lesson, data?.teachers ?: emptyList(), entries, u.absences, u.picks, coverFor(u), load, teacherParts, elsewhereFor(u))
    }

    /** "3 today + 1 cover · 24/week" - what a teacher already carries, beside their name. */
    fun loadText(teacherId: Int, forLesson: String): String {
        val u = _ui.value
        val today = Cover.lessonsToday(entries, Dates.weekday(u.date))[teacherId] ?: 0
        val cover = elsewhereFor(u).taken.count { it.second == teacherId } +
            coverFor(u).count { it.key != forLesson && u.picks[it.key] == teacherId }
        return "$today today${if (cover > 0) " + $cover cover" else ""} · ${load[teacherId] ?: 0}/week"
    }

    fun setDate(date: String) {
        dirty = false
        _ui.update { it.copy(date = date, note = null, error = null) }
        loadDay()
    }

    fun setPart(part: String) {
        if (part == _ui.value.part) return
        dirty = false
        _ui.update { it.copy(part = part, note = null, error = null, summary = null) }
        schoolId?.let { id -> viewModelScope.launch { c.store.setCoverPart(id, part) } }
        loadDay()
    }

    fun setAbsences(absences: Map<Int, Set<Int>?>) {
        dirty = true
        _ui.update { u ->
            // A lesson no longer needing cover drops its pick, so marking the teacher away again re-suggests.
            val still = coverFor(u.copy(absences = absences)).map { it.key }.toSet()
            u.copy(absences = absences, picks = u.picks.filterKeys { it in still }, note = null)
        }
        autofill()
    }

    fun pick(lessonKey: String, teacherId: Int?) {
        dirty = true
        _ui.update { it.copy(picks = it.picks + (lessonKey to teacherId), note = null) }
    }

    private fun loadDay() {
        val u = _ui.value
        val part = u.part
        val here = part?.let { p -> saved.firstOrNull { it.date == u.date && (it.category ?: Cover.WHOLE) == p } }
        _ui.update {
            it.copy(
                absences = here?.let { s -> Cover.absencesFrom(s) } ?: emptyMap(),
                picks = here?.let { s -> Cover.picksFrom(s, lessonsFor(u)) } ?: emptyMap(),
                savedToday = here != null,
                summary = if (here == null && isAdmin) null else it.summary,
            )
        }
        autofill()
        if (here != null || !isAdmin) loadSummary()
    }

    private var filling: Job? = null

    /** Finds each lesson's best free teacher in the background, so the screen never waits on it. */
    private fun autofill() {
        val d = data ?: return
        val snapshot = _ui.value
        if (snapshot.part == null) return
        val lessons = coverFor(snapshot)
        val all = entries
        val ld = load
        val tp = teacherParts
        val away = elsewhereFor(snapshot)
        filling?.cancel()
        filling = viewModelScope.launch {
            val picks = withContext(Dispatchers.Default) {
                Cover.autofill(lessons, d.teachers, all, snapshot.absences, snapshot.picks, ld, tp, away)
            }
            _ui.update {
                if (it.date == snapshot.date && it.part == snapshot.part && it.absences == snapshot.absences)
                    it.copy(picks = it.picks + picks.filterKeys { k -> k !in it.picks })
                else it
            }
        }
    }

    /** The summary for the date and part (a viewer who hasn't chosen sees the whole school). */
    private fun loadSummary() {
        val id = schoolId ?: return
        val date = _ui.value.date
        val part = _ui.value.part ?: Cover.WHOLE
        viewModelScope.launch {
            val s = runCatching { c.cover.summary(id, date, part.takeUnless { it == Cover.WHOLE }) }.getOrNull()
            if (_ui.value.date == date && (_ui.value.part ?: Cover.WHOLE) == part) _ui.update { it.copy(summary = s) }
        }
    }

    fun save() {
        val id = schoolId ?: return
        val u = _ui.value
        val part = u.part ?: return
        viewModelScope.launch {
            _ui.update { it.copy(busy = "save", error = null, note = null) }
            try {
                c.cover.save(id, Cover.body(u.date, part, u.absences, coverFor(u), u.picks))
                dirty = false
                _ui.update { it.copy(busy = null, savedToday = true, note = "Saved for ${Cover.partLabel(part).lowercase()}. Teachers can see it on the website and in the app.") }
                loadSummary()
            } catch (e: ApiException) {
                _ui.update { it.copy(busy = null, error = e.message) }
            }
        }
    }

    fun email() {
        val id = schoolId ?: return
        val date = _ui.value.date
        val part = _ui.value.part ?: return
        viewModelScope.launch {
            _ui.update { it.copy(busy = "email", error = null) }
            try {
                val r = c.cover.notify(id, date, part.takeUnless { it == Cover.WHOLE })
                val note = when {
                    !r.configured -> "Email isn't set up for Rivelle yet."
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
