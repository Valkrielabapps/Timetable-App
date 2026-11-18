package com.timetablz.app

import com.timetablz.app.data.Cover
import com.timetablz.app.data.Dates
import com.timetablz.app.data.Entry
import com.timetablz.app.data.Natural
import com.timetablz.app.data.Teacher
import com.timetablz.app.data.SavedChange
import com.timetablz.app.data.SavedCover
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
        val r = Cover.rank(first, teachers, entries, mapOf(1 to null), emptyMap(), lessons, load)
        // Bina has no lessons, so she works in no part of the school: listed last, as on the website.
        assertEquals(listOf("Chitra"), r.suggested.map { it.name })  // not Esha (unavailable), not Anil (away)
        assertEquals(listOf("Deepak"), r.same.map { it.name })
        assertEquals(listOf("Bina"), r.elsewhere.map { it.name })
    }

    @Test
    fun autofillNeverDoublesUpAndSkipsBusyTeachers() {
        val lessons = Cover.lessonsOn(entries, 0).filter { it.teacherId == 1 }
        val load = Cover.weeklyLoad(entries)
        val picks = Cover.autofill(lessons, teachers, entries, mapOf(1 to null), emptyMap(), load)
        assertEquals(3, picks[lessons.first { it.periodId == 10 }.key])
        assertEquals(3, picks[lessons.first { it.periodId == 11 }.key])  // different periods: Chitra can take both
    }

    // Two parts: sections 1-2 primary, 3-4 high.
    private val partOf = mapOf(1 to "primary", 2 to "primary", 3 to "high", 4 to "high")
    private val partEntries = listOf(
        entry(1, 1, maths, 1, 10),               // Anil, primary, P10
        entry(2, 3, maths, 1, 11),               // Anil, high, P11
        entry(3, 2, eng, 2, 12),                 // Bina works in primary
        entry(4, 4, eng, 3, 13),                 // Chitra works in high
        entry(5, 2, eng, 4, 13), entry(6, 1, eng, 4, 14),  // Deepak primary, heavier
    )

    @Test
    fun aPartShowsOnlyItsLessons() {
        val primary = Cover.lessonsOn(partEntries, 0, "primary", partOf)
        assertTrue(primary.all { it.part == "primary" })
        assertEquals(listOf(10, 12, 13, 14), primary.map { it.periodId })
        assertEquals(6, Cover.lessonsOn(partEntries, 0, Cover.WHOLE, partOf).size)
    }

    @Test
    fun suggestionsComeInThreeGroups() {
        val lessons = Cover.lessonsOn(partEntries, 0, "primary", partOf)
        val lesson = lessons.first { it.periodId == 10 }
        val tp = Cover.partsOfTeachers(partEntries, partOf)
        val r = Cover.rank(lesson, teachers, partEntries, mapOf(1 to null), emptyMap(), lessons,
            Cover.weeklyLoad(partEntries), tp)
        assertEquals(listOf("Bina"), r.suggested.map { it.name })   // Maths, in primary
        assertEquals(listOf("Deepak"), r.same.map { it.name })      // in primary, not Maths
        assertEquals(listOf("Chitra"), r.elsewhere.map { it.name }) // works in high
    }

    @Test
    fun awayForSomePeriodsOnly() {
        val absences = mapOf<Int, Set<Int>?>(1 to setOf(11))
        val lessons = Cover.lessonsOn(partEntries, 0, Cover.WHOLE, partOf)
        val toCover = lessons.filter { Cover.isAway(absences, it.teacherId, it.periodId) }
        assertEquals(listOf(11), toCover.map { it.periodId })
        assertTrue(Cover.isAway(mapOf(1 to null), 1, 99))
        assertFalse(Cover.isAway(absences, 1, 10))
    }

    @Test
    fun coverSavedForAnotherPartCounts() {
        val high = SavedCover(1, "2026-11-16", "high", setOf(3), listOf(SavedChange(10, 3, 2, 4, eng)),
            absences = mapOf(4 to listOf(10)))
        val away = Cover.elsewhere(listOf(high), "2026-11-16", "primary")
        assertTrue((10 to 2) in away.taken)                  // Bina already covers P10 in high
        assertEquals(mapOf<Int, Set<Int>?>(4 to setOf(10)), away.away)
        assertTrue(Cover.elsewhere(listOf(high), "2026-11-16", "high").taken.isEmpty())  // its own part
        assertTrue(Cover.elsewhere(listOf(high), "2026-11-17", "primary").taken.isEmpty())

        val lessons = Cover.lessonsOn(partEntries, 0, "primary", partOf)
        val lesson = lessons.first { it.periodId == 10 }
        val r = Cover.rank(lesson, teachers, partEntries, mapOf(1 to null), emptyMap(), lessons,
            Cover.weeklyLoad(partEntries), Cover.partsOfTeachers(partEntries, partOf), away)
        assertTrue(r.suggested.isEmpty())                     // Bina taken
        assertTrue(r.others.none { it.name == "Deepak" })     // Deepak away at P10 per the high-school cover
    }

    @Test
    fun olderSavedCoverGivesItsAbsencesFromTheLessons() {
        val old = SavedCover(1, "2026-11-16", null, emptySet(), listOf(SavedChange(10, 1, 2, 1, maths), SavedChange(11, 1, null, 3, maths)))
        assertEquals(mapOf<Int, Set<Int>?>(1 to setOf(10, 11)), Cover.absencesFrom(old))
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
