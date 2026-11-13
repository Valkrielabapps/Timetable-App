package com.timetablz.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Request and response shapes that differ from the app's own models.

@Serializable data class LoginRequest(val email: String, val password: String)
@Serializable data class GoogleRequest(val credential: String)
@Serializable data class TermsRequest(val version: String)
@Serializable data class NotifyRequest(val date: String, val everyone: Boolean = false)

@Serializable
data class TokenResponse(@SerialName("access_token") val accessToken: String, val user: User)

@Serializable data class AbsenceDto(@SerialName("teacher_id") val teacherId: Int, @SerialName("period_ids") val periodIds: List<Int>? = null)

@Serializable
data class ChangeDto(
    @SerialName("period_id") val periodId: Int,
    @SerialName("absent_teacher_id") val absentTeacherId: Int,
    @SerialName("substituting_teacher_id") val substituteId: Int? = null,
    @SerialName("class_group_id") val classGroupId: Int,
    @SerialName("subject_id") val subjectId: Int? = null,
)

@Serializable
data class CoverLogDto(
    val id: Int,
    val date: String? = null,
    val category: String? = null,
    val absences: List<AbsenceDto>? = null,
    val changes: List<ChangeDto> = emptyList(),
) {
    fun toDomain() = SavedCover(
        id = id, date = date, category = category,
        absentIds = absences.orEmpty().map { it.teacherId }.toSet(),
        changes = changes.map { SavedChange(it.periodId, it.absentTeacherId, it.substituteId, it.classGroupId, it.subjectId) },
    )
}

/** The whole school's cover for a day, whole-day absences (what the app makes). */
@Serializable
data class SaveCoverRequest(
    val date: String,
    val category: String? = null,
    val absences: List<AbsenceDto>,
    val changes: List<ChangeDto>,
)

@Serializable data class LeaveDto(val teacher: String)

@Serializable
data class RowDto(
    val period: String,
    @SerialName("class_group") val classGroup: String,
    val subject: String? = null,
    @SerialName("absent_teacher") val absentTeacher: String,
    val substitute: String? = null,
)

@Serializable
data class SummaryDto(
    val weekday: String = "",
    @SerialName("on_leave") val onLeave: List<LeaveDto> = emptyList(),
    val rows: List<RowDto> = emptyList(),
    val uncovered: Int = 0,
) {
    fun toDomain() = Summary(weekday, onLeave.map { it.teacher },
        rows.map { SummaryRow(it.period, it.classGroup, it.subject, it.absentTeacher, it.substitute) }, uncovered)
}

@Serializable
data class NotifyDto(
    @SerialName("email_configured") val configured: Boolean = true,
    val sent: List<String> = emptyList(),
    @SerialName("no_email") val noEmail: List<String> = emptyList(),
    val failed: List<String> = emptyList(),
    val reason: String? = null,
    val error: String? = null,
) {
    fun toDomain() = NotifyResult(configured, sent, noEmail, failed, reason ?: error)
}
