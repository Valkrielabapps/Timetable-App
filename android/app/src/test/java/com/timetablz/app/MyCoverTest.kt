package com.timetablz.app

import com.timetablz.app.data.Entry
import com.timetablz.app.data.MyCover
import com.timetablz.app.data.Period
import com.timetablz.app.data.SavedChange
import com.timetablz.app.data.SavedCover
import com.timetablz.app.data.Teacher
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MyCoverTest {
    private val teachers = listOf(
        Teacher(1, "Deva", "deva@school.in", setOf(1), emptySet()),
        Teacher(2, "Martina", "Martina@School.in", setOf(1), emptySet()),
    )

    @Test
    fun findsMeByEmailOrChoice() {
        assertEquals("Martina", MyCover.whoAmI(teachers, "martina@school.in ", null)?.name)
        assertEquals("Deva", MyCover.whoAmI(teachers, "martina@school.in", 1)?.name)
        assertNull(MyCover.whoAmI(teachers, "someone@else.com", null))
    }

    @Test
    fun listsTheLessonsIveBeenGiven() {
        val periods = listOf(Period(10, 0, 1, null, "lesson", 2), Period(11, 0, 6, null, "lesson", 7))
        val entries = listOf(
            Entry(1, 7, "7 A", 1, "Maths", 1, "Deva", 10, 0, 1, null, null),
            Entry(2, 9, "9 B", 1, "Maths", 1, "Deva", 11, 0, 6, null, null),
        )
        val covers = listOf(
            SavedCover(1, "2026-11-16", null, setOf(1), listOf(
                SavedChange(11, 1, 2, 9, 1),
                SavedChange(10, 1, 2, 7, 1),
                SavedChange(10, 1, null, 7, 1),
            )),
        )
        val mine = MyCover.of(2, covers, periods, entries, teachers, mapOf(1 to "Maths"))
        assertEquals(listOf("P2 7 A Maths", "P7 9 B Maths"), mine.map { "${it.periodLabel} ${it.classGroup} ${it.subject}" })
        assertEquals("Deva", mine[0].forTeacher)
    }

    @Test
    fun readsPeriodTimes() {
        assertEquals((9 to 0) to (9 to 45), MyCover.times("9:00-9:45"))
        assertEquals((13 to 30) to (14 to 15), MyCover.times("1.30 pm to 2.15 pm"))
        assertEquals((14 to 15) to (15 to 0), MyCover.times("2:15 - 3:00"))
        assertNull(MyCover.times("Period 3"))
    }
}
