package com.timetablz.app.data

/**
 * Cover for absent teachers - the same reasoning as the website's
 * Substitutions screen (frontend/src/components/SubstitutionsTab.jsx), so a
 * substitute picked on the phone is one the website would have suggested.
 */

/** One lesson to cover. A class taught to several sections at once is one lesson. */
data class Lesson(
    val key: String,
    val periodId: Int,
    val order: Int,
    val teacherId: Int,
    val teacherName: String,
    val subjectId: Int,
    val subjectName: String,
    val classGroupIds: List<Int>,
    val classGroupNames: List<String>,
    /** The part of the school its section is in ("primary", ...; null: in no part). */
    val part: String? = null,
)

/**
 * Who could take a lesson, in three groups, each lightest-loaded first:
 * suggested (teaches the subject and works in the lesson's part of the
 * school), same (works in that part) and elsewhere (other parts - another
 * building, so listed last).
 */
data class Ranked(val suggested: List<Teacher>, val same: List<Teacher>, val elsewhere: List<Teacher>) {
    val others get() = same + elsewhere
}

/** Cover already saved for the date in other parts of the school. */
data class Elsewhere(
    /** (period id, teacher id) of substitutes already taken there. */
    val taken: Set<Pair<Int, Int>> = emptySet(),
    /** Teachers away there: null all day, or those periods. */
    val away: Map<Int, Set<Int>?> = emptyMap(),
)

object Cover {
    const val WHOLE = "whole"

    /** The parts a school's cover is arranged by - the website's CATEGORIES. */
    val PARTS = listOf(
        "pre_primary" to "Pre-primary",
        "primary" to "Primary",
        "middle" to "Middle",
        "high" to "High school",
    )

    fun partLabel(key: String?): String = when (key) {
        WHOLE -> "Whole school"
        else -> PARTS.firstOrNull { it.first == key }?.second ?: "Other"
    }

    /** Away at that period: absences hold null (all day) or the periods away. */
    fun isAway(absences: Map<Int, Set<Int>?>, teacherId: Int, periodId: Int): Boolean =
        teacherId in absences && absences[teacherId].let { it == null || periodId in it }

    /**
     * The day's lessons that have a teacher, in period order - for one part of
     * the school ([partOf]: section id -> part), or all of it for [WHOLE].
     */
    fun lessonsOn(
        entries: List<Entry>,
        day: Int,
        part: String = WHOLE,
        partOf: Map<Int, String?> = emptyMap(),
    ): List<Lesson> =
        entries.filter { it.day == day && it.teacherId != null && (part == WHOLE || partOf[it.classGroupId] == part) }
            .groupBy { Triple(it.periodId, it.teacherId!!, it.subjectId) }
            .map { (k, es) ->
                val first = es.first()
                Lesson(
                    key = "${k.first}:${k.second}:${k.third}",
                    periodId = k.first,
                    order = first.order,
                    teacherId = k.second,
                    teacherName = first.teacherName ?: "",
                    subjectId = k.third,
                    subjectName = first.subjectName,
                    classGroupIds = es.map { it.classGroupId }.distinct(),
                    classGroupNames = es.map { it.classGroupName }.distinct(),
                    part = partOf[first.classGroupId],
                )
            }
            .sortedWith(compareBy({ it.order }, { it.teacherName }))

    /** Lessons each teacher teaches in the week - lighter-loaded teachers are suggested first. */
    fun weeklyLoad(entries: List<Entry>): Map<Int, Int> =
        entries.mapNotNull { it.teacherId?.let { t -> t to it.periodId } }.distinct()
            .groupingBy { it.first }.eachCount()

    /** Lessons each teacher has on [day], across the whole school. */
    fun lessonsToday(entries: List<Entry>, day: Int): Map<Int, Int> = weeklyLoad(entries.filter { it.day == day })

    /** The parts of the school each teacher works in over the week - the building they're usually in. */
    fun partsOfTeachers(entries: List<Entry>, partOf: Map<Int, String?>): Map<Int, Set<String?>> =
        entries.filter { it.teacherId != null }
            .groupBy({ it.teacherId!! }, { partOf[it.classGroupId] })
            .mapValues { it.value.toSet() }

    /** What's saved for [date] in parts of the school other than [part]. */
    fun elsewhere(saved: List<SavedCover>, date: String, part: String): Elsewhere {
        val taken = mutableSetOf<Pair<Int, Int>>()
        val away = mutableMapOf<Int, Set<Int>?>()
        for (log in saved) {
            if (log.date != date || (log.category ?: WHOLE) == part) continue
            log.changes.forEach { c -> c.substituteId?.let { taken += c.periodId to it } }
            for ((t, ids) in log.absences) {
                if (ids == null) away[t] = null
                else if (!(t in away && away[t] == null)) away[t] = (away[t] ?: emptySet()) + ids
            }
        }
        return Elsewhere(taken, away)
    }

    /**
     * Who could take [lesson]: free at that period - no lesson of their own,
     * not away (here or in another part's saved cover), not marked
     * unavailable, not already covering another lesson then (here or
     * elsewhere). Then three groups, as on the website.
     */
    fun rank(
        lesson: Lesson,
        teachers: List<Teacher>,
        entries: List<Entry>,
        absences: Map<Int, Set<Int>?>,
        picks: Map<String, Int?>,
        lessons: List<Lesson>,
        load: Map<Int, Int>,
        teacherParts: Map<Int, Set<String?>> = partsOfTeachers(entries, emptyMap()),
        elsewhere: Elsewhere = Elsewhere(),
    ): Ranked {
        val p = lesson.periodId
        val busy = entries.filter { it.periodId == p }.mapNotNull { it.teacherId }.toSet()
        val pickedThen = lessons.filter { it.key != lesson.key && it.periodId == p }
            .mapNotNull { picks[it.key] }.toSet()
        val free = teachers.filter {
            it.id !in busy && !isAway(absences, it.id, p) && !isAway(elsewhere.away, it.id, p) &&
                p !in it.unavailablePeriodIds && it.id !in pickedThen && (p to it.id) !in elsewhere.taken
        }.sortedWith(compareBy({ load[it.id] ?: 0 }, { it.name.lowercase() }))
        val (here, other) = free.partition { teacherParts[it.id]?.contains(lesson.part) == true }
        val (qualified, rest) = here.partition { lesson.subjectId in it.subjectIds }
        return Ranked(qualified, rest, other)
    }

    /** Every uncovered lesson given its top suggestion, in period order, never doubling anyone up. */
    fun autofill(
        lessons: List<Lesson>,
        teachers: List<Teacher>,
        entries: List<Entry>,
        absences: Map<Int, Set<Int>?>,
        picks: Map<String, Int?>,
        load: Map<Int, Int>,
        teacherParts: Map<Int, Set<String?>> = partsOfTeachers(entries, emptyMap()),
        elsewhere: Elsewhere = Elsewhere(),
    ): Map<String, Int?> {
        val next = picks.toMutableMap()
        for (l in lessons) {
            if (l.key in next) continue
            rank(l, teachers, entries, absences, next, lessons, load, teacherParts, elsewhere)
                .suggested.firstOrNull()?.let { next[l.key] = it.id }
        }
        return next
    }

    /**
     * What the server stores for the day and part: who's away (null periods =
     * all day) and each lesson to cover. Someone set to "some periods" with
     * none ticked isn't away at all.
     */
    fun body(date: String, part: String, absences: Map<Int, Set<Int>?>, lessons: List<Lesson>, picks: Map<String, Int?>) =
        SaveCoverRequest(
            date = date,
            category = part.takeUnless { it == WHOLE },
            absences = absences.filter { it.value == null || it.value!!.isNotEmpty() }.toSortedMap()
                .map { (t, ids) -> AbsenceDto(t, ids?.sorted()) },
            changes = lessons.flatMap { l ->
                l.classGroupIds.map { cg -> ChangeDto(l.periodId, l.teacherId, picks[l.key], cg, l.subjectId) }
            },
        )

    /** Who was away in saved cover; older records kept only the lessons covered. */
    fun absencesFrom(saved: SavedCover): Map<Int, Set<Int>?> =
        if (saved.absences.isNotEmpty()) saved.absences.mapValues { it.value?.toSet() }
        else saved.changes.groupBy({ it.absentTeacherId }, { it.periodId }).mapValues { it.value.toSet() }

    /** Picks from cover already saved for the day, keyed like [Lesson.key]. */
    fun picksFrom(saved: SavedCover, lessons: List<Lesson>): Map<String, Int?> {
        val out = mutableMapOf<String, Int?>()
        for (l in lessons) {
            val c = saved.changes.firstOrNull { it.periodId == l.periodId && it.absentTeacherId == l.teacherId && it.classGroupId in l.classGroupIds }
            if (c != null) out[l.key] = c.substituteId
        }
        return out
    }

    /** The summary as a WhatsApp message (*bold* is WhatsApp's own markup) - the website's summaryText. */
    fun summaryText(s: Summary): String {
        val lines = mutableListOf("*Substitutions - ${if (s.date.isNotBlank()) Dates.long(s.date) else s.weekday}*", s.partLabel)
        if (s.onLeave.isNotEmpty()) lines += listOf("", "*On leave:* ${s.onLeave.joinToString(", ") { it.text }}")
        if (s.rows.isEmpty()) lines += listOf("", "No lessons need cover.")
        val groups = if (s.part != null) listOf(s.partLabel to s.rows).filter { it.second.isNotEmpty() }
        else (PARTS.map { it.first } + listOf(null))
            .map { key -> partLabel(key) to s.rows.filter { it.part == key } }
            .filter { it.second.isNotEmpty() }
        for ((label, rows) in groups) {
            lines += ""
            if (s.part == null) lines += "*$label*"
            for (r in rows) {
                val lesson = listOfNotNull(r.period, r.classGroup, r.subject).filter { it.isNotBlank() }.joinToString(" · ")
                lines += "$lesson: ${r.absent} → ${r.substitute ?: "*NOT COVERED*"}"
            }
        }
        if (s.uncovered > 0) {
            val n = s.uncovered
            lines += listOf("", "⚠️ $n period${if (n == 1) "" else "s"} still need${if (n == 1) "s" else ""} cover.")
        }
        return lines.joinToString("\n")
    }
}
