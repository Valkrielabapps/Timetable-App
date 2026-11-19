package com.timetablz.app

import com.timetablz.app.data.Entry
import com.timetablz.app.data.Period
import com.timetablz.app.data.WeekCell
import com.timetablz.app.data.WeekCells
import com.timetablz.app.data.WeekLayout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WeekTest {
    // Mon and Tue: P1, a break, P2. Saturday has only a break, so it isn't a column.
    private val periods = listOf(
        Period(1, 0, 1, null, "lesson", 1), Period(2, 0, 2, "Recess", "break"), Period(3, 0, 3, null, "lesson", 2),
        Period(4, 1, 1, null, "lesson", 1), Period(5, 1, 2, "Recess", "break"), Period(6, 1, 3, null, "lesson", 2),
        Period(7, 5, 1, "Assembly", "break"),
    )

    private fun entry(id: Int, section: Int, sectionName: String, subject: String, teacher: Int?, teacherName: String?, period: Int, block: String? = null) =
        Entry(id, section, sectionName, 1, subject, teacher, teacherName, period, 0, 1, null, block)

    @Test
    fun laysOutDaysAcrossAndSlotsDown() {
        val layout = WeekLayout(periods)
        assertEquals(listOf(0, 1), layout.days)
        assertEquals(listOf("P1", "Recess", "P2"), layout.rows.map { it.label })
        assertEquals(listOf(false, true, false), layout.rows.map { it.band })
        assertEquals(6, layout.at(1, 3)?.id)
        assertNull(layout.at(2, 1))
    }

    @Test
    fun aTeachersCellNamesTheSectionsShortly() {
        val entries = listOf(
            entry(1, 6, "Grade 6 A", "Maths", 9, "Deva", 1),
            entry(2, 7, "Grade 6 B", "Maths", 9, "Deva", 1),
            entry(3, 8, "Grade 7 A", "Science", 4, "Martina", 3),
        )
        assertEquals(mapOf(1 to WeekCell("Maths", listOf("6 A, 6 B"))), WeekCells.forTeacher(entries, 9))
        assertEquals(setOf(9, 4), WeekCells.forEveryTeacher(entries).keys)
    }

    @Test
    fun aSectionsCellNamesTheTeacherOrTheBlock() {
        val entries = listOf(
            entry(1, 6, "Grade 6 A", "Maths", 9, "Deva", 1),
            entry(2, 6, "Grade 6 A", "French", 4, "Martina", 3, block = "Languages"),
            entry(3, 6, "Grade 6 A", "German", 5, "Ravi", 3, block = "Languages"),
            entry(4, 6, "Grade 6 A", "Art", null, null, 4),
        )
        val cells = WeekCells.forSection(entries, 6)
        assertEquals(WeekCell("Maths", listOf("Deva")), cells[1])
        assertEquals(WeekCell("Languages", listOf("Martina", "Ravi")), cells[3])
        assertEquals(WeekCell("Art", listOf("No teacher yet")), cells[4])
    }

    @Test
    fun shortensSectionNames() {
        assertEquals("6 A", WeekCells.shortSection("Grade 6 A"))
        assertEquals("10 B", WeekCells.shortSection("class 10 B"))
        assertEquals("Nursery A", WeekCells.shortSection("Nursery A"))
    }
}
