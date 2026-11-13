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
)

data class Ranked(val suggested: List<Teacher>, val others: List<Teacher>)

object Cover {

    /** The day's lessons that have a teacher, in period order. */
    fun lessonsOn(entries: List<Entry>, day: Int): List<Lesson> =
        entries.filter { it.day == day && it.teacherId != null }
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
                )
            }
            .sortedWith(compareBy({ it.order }, { it.teacherName }))

    /** Lessons each teacher teaches in the week - lighter-loaded teachers are suggested first. */
    fun weeklyLoad(entries: List<Entry>): Map<Int, Int> =
        entries.mapNotNull { it.teacherId?.let { t -> t to it.periodId } }.distinct()
            .groupingBy { it.first }.eachCount()

    /**
     * Who could take [lesson]: free at that period (no lesson of their own,
     * not away, not marked unavailable, not already covering another lesson
     * then). Suggested = qualified for the subject; then everyone else free.
     * Each list lightest-loaded first.
     */
    fun rank(
        lesson: Lesson,
        teachers: List<Teacher>,
        entries: List<Entry>,
        absent: Set<Int>,
        picks: Map<String, Int?>,
        lessons: List<Lesson>,
        load: Map<Int, Int>,
    ): Ranked {
        val busy = entries.filter { it.periodId == lesson.periodId }.mapNotNull { it.teacherId }.toSet()
        val pickedThen = lessons.filter { it.key != lesson.key && it.periodId == lesson.periodId }
            .mapNotNull { picks[it.key] }.toSet()
        val free = teachers.filter {
            it.id !in busy && it.id !in absent && lesson.periodId !in it.unavailablePeriodIds && it.id !in pickedThen
        }.sortedWith(compareBy({ load[it.id] ?: 0 }, { it.name.lowercase() }))
        val (qualified, rest) = free.partition { lesson.subjectId in it.subjectIds }
        return Ranked(qualified, rest)
    }

    /** Every uncovered lesson given its top suggestion, in period order, never doubling anyone up. */
    fun autofill(
        lessons: List<Lesson>,
        teachers: List<Teacher>,
        entries: List<Entry>,
        absent: Set<Int>,
        picks: Map<String, Int?>,
        load: Map<Int, Int>,
    ): Map<String, Int?> {
        val next = picks.toMutableMap()
        for (l in lessons) {
            if (l.key in next) continue
            rank(l, teachers, entries, absent, next, lessons, load).suggested.firstOrNull()?.let { next[l.key] = it.id }
        }
        return next
    }

    /** What the server stores for the day (whole school; whole-day absences). */
    fun body(date: String, absent: Set<Int>, lessons: List<Lesson>, picks: Map<String, Int?>) = SaveCoverRequest(
        date = date,
        absences = absent.sorted().map { AbsenceDto(it) },
        changes = lessons.flatMap { l ->
            l.classGroupIds.map { cg -> ChangeDto(l.periodId, l.teacherId, picks[l.key], cg, l.subjectId) }
        },
    )

    /** Picks from cover already saved for the day, keyed like [Lesson.key]. */
    fun picksFrom(saved: SavedCover, lessons: List<Lesson>): Map<String, Int?> {
        val out = mutableMapOf<String, Int?>()
        for (l in lessons) {
            val c = saved.changes.firstOrNull { it.periodId == l.periodId && it.absentTeacherId == l.teacherId && it.classGroupId in l.classGroupIds }
            if (c != null) out[l.key] = c.substituteId
        }
        return out
    }
}
