package com.timetablz.app

import com.timetablz.app.data.Cover
import com.timetablz.app.data.Dates
import com.timetablz.app.data.Entry
import com.timetablz.app.data.Natural
import com.timetablz.app.data.Teacher
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CoverTest {
    private val maths = 1
    private val eng = 2

    private fun entry(id: Int, cg: Int, subject: Int, teacher: Int, period: Int, day: Int = 0) =
        Entry(id, cg, "6 $cg", subject, if (subject == maths) "Maths" else "English", teacher, "T$teacher",
            period, day, period, null, null)

    private val teachers = listOf(
        Teacher(1, "Anil", null, setOf(maths), emptySet()),      // away
        Teacher(2, "Bina", null, setOf(maths), emptySet()),      // free, teaches Maths, light
        Teacher(3, "Chitra", null, setOf(maths), emptySet()),    // free, teaches Maths, heavier
        Teacher(4, "Deepak", null, setOf(eng), emptySet()),      // free, not Maths
        Teacher(5, "Esha", null, setOf(maths), setOf(10)),       // unavailable in period 10
    )

    private val entries = listOf(
        entry(1, 1, maths, 1, 10),
        entry(2, 2, maths, 1, 11),
        entry(3, 3, eng, 3, 12), entry(4, 4, eng, 3, 13),  // Chitra busier
        entry(5, 5, eng, 4, 11),                            // Deepak busy in 11
    )

    @Test
    fun suggestsFreeQualifiedTeachersLightestFirst() {
        val lessons = Cover.lessonsOn(entries, 0)
        val load = Cover.weeklyLoad(entries)
        val first = lessons.first { it.periodId == 10 }
        val r = Cover.rank(first, teachers, entries, setOf(1), emptyMap(), lessons, load)
        assertEquals(listOf("Bina", "Chitra"), r.suggested.map { it.name })  // not Esha (unavailable), not Anil (away)
        assertEquals(listOf("Deepak"), r.others.map { it.name })
    }

    @Test
    fun autofillNeverDoublesUpAndSkipsBusyTeachers() {
        val lessons = Cover.lessonsOn(entries, 0).filter { it.teacherId == 1 }
        val load = Cover.weeklyLoad(entries)
        val picks = Cover.autofill(lessons, teachers, entries, setOf(1), emptyMap(), load)
        assertEquals(2, picks[lessons.first { it.periodId == 10 }.key])
        assertEquals(2, picks[lessons.first { it.periodId == 11 }.key])  // different periods: Bina can take both
    }

    @Test
    fun aClassForSeveralSectionsIsOneLesson() {
        val shared = listOf(entry(1, 1, maths, 1, 10), entry(2, 2, maths, 1, 10))
        val lessons = Cover.lessonsOn(shared, 0)
        assertEquals(1, lessons.size)
        assertEquals(listOf(1, 2), lessons[0].classGroupIds)
    }

    @Test
    fun sectionsSortNaturally() {
        val sorted = listOf("Grade 10 A", "Grade 2 B", "Grade 2 A").sortedWith(Natural)
        assertEquals(listOf("Grade 2 A", "Grade 2 B", "Grade 10 A"), sorted)
    }

    @Test
    fun datesCountMondayAsZero() {
        assertEquals(4, Dates.weekday("2026-11-13"))  // a Friday
        assertEquals("2026-11-14", Dates.add("2026-11-13", 1))
        assertTrue(Dates.weekday(Dates.today()) in 0..6)
    }
}
