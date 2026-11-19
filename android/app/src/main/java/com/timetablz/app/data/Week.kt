package com.timetablz.app.data

/**
 * The website's week grid: days across, the school's slots down. A row is a
 * band (break, lunch) when no day has a lesson in that slot.
 */
class WeekLayout(periods: List<Period>) {
    data class Row(val order: Int, val label: String, val band: Boolean)

    private val byDayOrder = periods.associateBy { it.day to it.order }
    val days: List<Int> = periods.filter { it.isLesson }.map { it.day }.distinct().sorted()
    val rows: List<Row> = periods.groupBy { it.order }.toSortedMap().map { (order, here) ->
        val lesson = here.firstOrNull { it.isLesson && it.day in days }
        if (lesson != null) Row(order, lesson.short, band = false)
        else Row(order, here.firstNotNullOfOrNull { it.label } ?: "Break", band = true)
    }

    fun at(day: Int, order: Int): Period? = byDayOrder[day to order]
}

/** What one cell of a week grid says: the subject, then who teaches it (each teacher on a line) or which sections. */
data class WeekCell(val top: String, val lines: List<String>)

object WeekCells {
    /** "Grade 6 A" -> "6 A": room for it in a small cell. */
    fun shortSection(name: String): String = name.trim().replace(Regex("^(Grade|Class|Std\\.?)\\s+", RegexOption.IGNORE_CASE), "")

    /** Period id -> cell, for one teacher's week. */
    fun forTeacher(entries: List<Entry>, teacherId: Int): Map<Int, WeekCell> =
        entries.filter { it.teacherId == teacherId }.groupBy { it.periodId }.mapValues { (_, here) ->
            WeekCell(here.first().subjectName, listOf(here.map { shortSection(it.classGroupName) }.distinct().joinToString(", ")))
        }

    /** Period id -> cell, for one section's week. */
    fun forSection(entries: List<Entry>, sectionId: Int): Map<Int, WeekCell> =
        entries.filter { it.classGroupId == sectionId }.groupBy { it.periodId }.mapValues { (_, here) -> sectionCell(here) }

    /** Every teacher's or section's week at once, worked out in one pass. */
    fun forEveryTeacher(entries: List<Entry>): Map<Int, Map<Int, WeekCell>> =
        entries.filter { it.teacherId != null }.groupBy { it.teacherId!! }.mapValues { (id, mine) -> forTeacher(mine, id) }

    fun forEverySection(entries: List<Entry>): Map<Int, Map<Int, WeekCell>> =
        entries.groupBy { it.classGroupId }.mapValues { (id, mine) -> forSection(mine, id) }

    private fun sectionCell(here: List<Entry>): WeekCell {
        val first = here.first()
        val teachers = here.map { it.teacherName ?: "No teacher yet" }.distinct()
        // An elective block splits the section into groups with different teachers;
        // lab batches have a teacher each. Every teacher is named.
        return WeekCell(if (first.blockName != null && here.size > 1) first.blockName else first.subjectName, teachers)
    }
}
