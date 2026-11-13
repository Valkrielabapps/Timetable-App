package com.timetablz.app

import com.timetablz.app.data.CoverLogDto
import com.timetablz.app.data.Cover
import com.timetablz.app.data.Lesson
import com.timetablz.app.data.Network
import com.timetablz.app.data.SchoolData
import com.timetablz.app.data.Teacher
import com.timetablz.app.data.Timetable
import com.timetablz.app.data.TokenResponse
import kotlinx.serialization.builtins.ListSerializer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The backend's JSON, as it really comes, read into the app's models - and written back for saving. */
class ApiShapesTest {
    private val json = Network.json

    @Test
    fun signInAndTeachers() {
        val t = json.decodeFromString(TokenResponse.serializer(), """
            {"access_token":"abc","token_type":"bearer","user":{"id":3,"email":"a@b.in","name":null,
             "is_platform_admin":false,"needs_terms":true,"terms_version":"2026-11-09","has_accepted_before":false}}""")
        assertEquals("abc", t.accessToken)
        assertTrue(t.user.needsTerms)
        val teachers = json.decodeFromString(ListSerializer(Teacher.serializer()), """
            [{"id":1,"school_id":9,"name":"Deva","email":null,"qualified_subject_ids":[4,5],"qualified_grades":null,
              "unavailable_period_ids":[],"max_periods_per_week":null,"is_assistant_eligible":false}]""")
        assertEquals(setOf(4, 5), teachers[0].subjectIds)
        assertNull(teachers[0].email)
    }

    @Test
    fun aTimetableAndItsOfflineCopy() {
        val tt = json.decodeFromString(Timetable.serializer(), """
            {"id":7,"school_id":9,"status":"draft","solver_status":"optimal","error_message":null,"entries":[
              {"id":1,"class_group_id":2,"class_group_name":"Grade 7 A","subject_id":4,"subject_name":"Maths",
               "teacher_id":1,"teacher_name":"Deva","assistant_teacher_id":null,"period_id":10,"period_label":"P2",
               "day_of_week":0,"order":1,"room_id":null,"room_name":null,"locked":false,"elective_block_name":null}]}""")
        assertEquals("Grade 7 A", tt.entries[0].classGroupName)
        // The cache stores it and reads it back the same.
        val data = SchoolData(emptyList(), emptyList(), tt)
        val back = json.decodeFromString(SchoolData.serializer(), json.encodeToString(SchoolData.serializer(), data))
        assertEquals(data, back)
    }

    @Test
    fun savedCoverAndSavingIt() {
        val log = json.decodeFromString(CoverLogDto.serializer(), """
            {"id":5,"school_id":9,"day_of_week":0,"date":"2026-11-16","category":null,
             "absences":[{"teacher_id":1,"period_ids":null}],"created_at":"2026-11-16T07:00:00",
             "changes":[{"period_id":10,"absent_teacher_id":1,"substituting_teacher_id":2,"class_group_id":2,"subject_id":4,"category":"middle"}]}""")
            .toDomain()
        assertEquals(setOf(1), log.absentIds)
        assertEquals(2, log.changes[0].substituteId)

        val lesson = Lesson("10:1:4", 10, 1, 1, "Deva", 4, "Maths", listOf(2, 3), listOf("7 A", "7 B"))
        val body = json.encodeToString(com.timetablz.app.data.SaveCoverRequest.serializer(),
            Cover.body("2026-11-16", setOf(1), listOf(lesson), mapOf(lesson.key to null)))
        assertTrue(body.contains("\"absent_teacher_id\":1"))
        assertTrue(body.contains("\"class_group_id\":3"))  // one change per section of a shared class
        assertFalse(body.contains("substituting_teacher_id"))  // uncovered: left out, the server reads it as none
    }
}
