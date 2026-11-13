package com.timetablz.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// The app's own picture of a school. The API's JSON maps straight onto most
// of these (field names via @SerialName); the rest come from Dto.kt. They're
// also what the offline cache stores.

@Serializable
data class User(
    val id: Int,
    val email: String,
    val name: String? = null,
    @SerialName("needs_terms") val needsTerms: Boolean = false,
    @SerialName("terms_version") val termsVersion: String = "",
)

@Serializable
data class School(val id: Int, val name: String, val role: String = "viewer") {
    val isAdmin get() = role == "admin"
}

@Serializable
data class Period(
    val id: Int,
    @SerialName("day_of_week") val day: Int,
    val order: Int,
    val label: String? = null,
    val kind: String = "lesson",
    val number: Int? = null,
) {
    val isLesson get() = kind == "lesson"
    /** "P3", or the slot's own label for a break. */
    val short get() = number?.let { "P$it" } ?: (label ?: "")
}

/** A section: grade "Grade 6", name "A". */
@Serializable
data class ClassGroup(val id: Int, val name: String, val grade: String? = null) {
    /** "Grade 6 A" - how the app names a section everywhere. */
    val label get() = sectionLabel(grade, name)
}

/** "Grade 6" + "A" -> "Grade 6 A"; a name that already starts with its grade is left alone. */
fun sectionLabel(grade: String?, name: String): String {
    val g = grade?.trim().orEmpty()
    return if (g.isEmpty() || name.trim().startsWith(g, ignoreCase = true)) name.trim() else "$g ${name.trim()}"
}

@Serializable
data class Teacher(
    val id: Int,
    val name: String,
    val email: String? = null,
    @SerialName("qualified_subject_ids") val subjectIds: Set<Int> = emptySet(),
    @SerialName("unavailable_period_ids") val unavailablePeriodIds: Set<Int> = emptySet(),
)

@Serializable
data class Entry(
    val id: Int,
    @SerialName("class_group_id") val classGroupId: Int,
    @SerialName("class_group_name") val classGroupName: String = "",
    @SerialName("subject_id") val subjectId: Int,
    @SerialName("subject_name") val subjectName: String = "",
    @SerialName("teacher_id") val teacherId: Int? = null,
    @SerialName("teacher_name") val teacherName: String? = null,
    @SerialName("period_id") val periodId: Int,
    @SerialName("day_of_week") val day: Int,
    val order: Int,
    @SerialName("room_name") val roomName: String? = null,
    @SerialName("elective_block_name") val blockName: String? = null,
)

@Serializable
data class TimetableSummary(
    val id: Int,
    val status: String,
    @SerialName("is_current") val isCurrent: Boolean = false,
    @SerialName("version_number") val versionNumber: Int? = null,
    val name: String? = null,
)

@Serializable
data class Timetable(val id: Int, val entries: List<Entry> = emptyList())

/** Everything one school's screens read, cached together. */
@Serializable
data class SchoolData(val periods: List<Period>, val teachers: List<Teacher>, val timetable: Timetable?)

@Serializable
data class SavedChange(val periodId: Int, val absentTeacherId: Int, val substituteId: Int?, val classGroupId: Int, val subjectId: Int? = null)

@Serializable
data class SavedCover(val id: Int, val date: String?, val category: String?, val absentIds: Set<Int>, val changes: List<SavedChange>)

data class SummaryRow(val period: String, val classGroup: String, val subject: String?, val absent: String, val substitute: String?)

data class Summary(val weekday: String, val onLeave: List<String>, val rows: List<SummaryRow>, val uncovered: Int)

data class NotifyResult(val configured: Boolean, val sent: List<String>, val noEmail: List<String>, val failed: List<String>, val reason: String?)
