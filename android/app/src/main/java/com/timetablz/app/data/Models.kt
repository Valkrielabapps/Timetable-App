package com.timetablz.app.data

import org.json.JSONArray
import org.json.JSONObject

// What the app reads from the Timetablz API (the same one the website uses).
// Parsed with Android's built-in org.json, so the app needs no extra libraries.

data class User(val id: Int, val email: String, val name: String?, val needsTerms: Boolean, val termsVersion: String)

data class School(val id: Int, val name: String, val role: String) {
    val isAdmin get() = role == "admin"
}

data class Period(val id: Int, val day: Int, val order: Int, val label: String?, val kind: String, val number: Int?) {
    val isLesson get() = kind == "lesson"
    /** "P3", or the slot's own label for a break. */
    val short get() = number?.let { "P$it" } ?: (label ?: "")
}

data class Teacher(
    val id: Int,
    val name: String,
    val email: String?,
    val subjectIds: Set<Int>,
    val unavailablePeriodIds: Set<Int>,
)

data class Entry(
    val id: Int,
    val classGroupId: Int,
    val classGroupName: String,
    val subjectId: Int,
    val subjectName: String,
    val teacherId: Int?,
    val teacherName: String?,
    val periodId: Int,
    val day: Int,
    val order: Int,
    val roomName: String?,
    val blockName: String?,
)

data class TimetableSummary(val id: Int, val status: String, val isCurrent: Boolean, val versionNumber: Int?, val name: String?)

data class Timetable(val id: Int, val entries: List<Entry>)

data class SavedChange(val periodId: Int, val absentTeacherId: Int, val substituteId: Int?, val classGroupId: Int)

data class SavedCover(val id: Int, val date: String?, val category: String?, val absentIds: Set<Int>, val changes: List<SavedChange>)

data class SummaryRow(val period: String, val classGroup: String, val subject: String?, val absent: String, val substitute: String?)

data class Summary(val weekday: String, val onLeave: List<String>, val rows: List<SummaryRow>, val uncovered: Int)

data class NotifyResult(val configured: Boolean, val sent: List<String>, val noEmail: List<String>, val failed: List<String>, val reason: String?)

// ------------------------------------------------------------------ parsing

private fun JSONObject.optStr(key: String): String? = if (isNull(key)) null else optString(key)
private fun JSONObject.optIntOrNull(key: String): Int? = if (isNull(key) || !has(key)) null else optInt(key)

private fun JSONArray.ints(): Set<Int> = (0 until length()).map { getInt(it) }.toSet()
private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }
private inline fun <T> JSONArray.map(f: (JSONObject) -> T): List<T> = (0 until length()).map { f(getJSONObject(it)) }

fun parseUser(o: JSONObject) = User(
    id = o.getInt("id"),
    email = o.getString("email"),
    name = o.optStr("name"),
    needsTerms = o.optBoolean("needs_terms", false),
    termsVersion = o.optString("terms_version", ""),
)

fun parseSchools(a: JSONArray) = a.map { School(it.getInt("id"), it.getString("name"), it.optString("role", "viewer")) }

fun parsePeriods(a: JSONArray) = a.map {
    Period(it.getInt("id"), it.getInt("day_of_week"), it.getInt("order"), it.optStr("label"),
        it.optString("kind", "lesson"), it.optIntOrNull("number"))
}

fun parseTeachers(a: JSONArray) = a.map {
    Teacher(
        id = it.getInt("id"),
        name = it.getString("name"),
        email = it.optStr("email"),
        subjectIds = it.optJSONArray("qualified_subject_ids")?.ints() ?: emptySet(),
        unavailablePeriodIds = it.optJSONArray("unavailable_period_ids")?.ints() ?: emptySet(),
    )
}

fun parseTimetables(a: JSONArray) = a.map {
    TimetableSummary(it.getInt("id"), it.getString("status"), it.optBoolean("is_current", false),
        it.optIntOrNull("version_number"), it.optStr("name"))
}

fun parseTimetable(o: JSONObject) = Timetable(
    id = o.getInt("id"),
    entries = (o.optJSONArray("entries") ?: JSONArray()).map {
        Entry(
            id = it.getInt("id"),
            classGroupId = it.getInt("class_group_id"),
            classGroupName = it.optString("class_group_name"),
            subjectId = it.getInt("subject_id"),
            subjectName = it.optString("subject_name"),
            teacherId = it.optIntOrNull("teacher_id"),
            teacherName = it.optStr("teacher_name"),
            periodId = it.getInt("period_id"),
            day = it.getInt("day_of_week"),
            order = it.getInt("order"),
            roomName = it.optStr("room_name"),
            blockName = it.optStr("elective_block_name"),
        )
    },
)

fun parseCovers(a: JSONArray) = a.map { o ->
    SavedCover(
        id = o.getInt("id"),
        date = o.optStr("date"),
        category = o.optStr("category"),
        absentIds = (o.optJSONArray("absences") ?: JSONArray()).map { it.getInt("teacher_id") }.toSet(),
        changes = (o.optJSONArray("changes") ?: JSONArray()).map {
            SavedChange(it.getInt("period_id"), it.getInt("absent_teacher_id"),
                it.optIntOrNull("substituting_teacher_id"), it.getInt("class_group_id"))
        },
    )
}

fun parseSummary(o: JSONObject) = Summary(
    weekday = o.optString("weekday"),
    onLeave = (o.optJSONArray("on_leave") ?: JSONArray()).map { it.getString("teacher") },
    rows = (o.optJSONArray("rows") ?: JSONArray()).map {
        SummaryRow(it.getString("period"), it.getString("class_group"), it.optStr("subject"),
            it.getString("absent_teacher"), it.optStr("substitute"))
    },
    uncovered = o.optInt("uncovered", 0),
)

fun parseNotify(o: JSONObject) = NotifyResult(
    configured = o.optBoolean("email_configured", true),
    sent = o.optJSONArray("sent")?.strings() ?: emptyList(),
    noEmail = o.optJSONArray("no_email")?.strings() ?: emptyList(),
    failed = o.optJSONArray("failed")?.strings() ?: emptyList(),
    reason = o.optStr("reason") ?: o.optStr("error"),
)
