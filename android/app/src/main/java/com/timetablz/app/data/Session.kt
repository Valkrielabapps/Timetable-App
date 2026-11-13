package com.timetablz.app.data

import android.content.Context

/** What the app remembers between launches: who's signed in and which school. */
class Session(context: Context) {
    private val prefs = context.getSharedPreferences("timetablz", Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString("token", null)
        set(v) = prefs.edit().putString("token", v).apply()

    var schoolId: Int?
        get() = prefs.getInt("school_id", -1).takeIf { it > 0 }
        set(v) = prefs.edit().putInt("school_id", v ?: -1).apply()

    var timetableView: String
        get() = prefs.getString("timetable_view", "section") ?: "section"
        set(v) = prefs.edit().putString("timetable_view", v).apply()

    fun signOut() = prefs.edit().remove("token").remove("school_id").apply()
}
