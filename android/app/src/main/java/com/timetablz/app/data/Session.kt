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

    /** "system", "light" or "dark". */
    var theme: String
        get() = prefs.getString("theme", "system") ?: "system"
        set(v) = prefs.edit().putString("theme", v).apply()

    /** Notify me when I'm given cover. */
    var notifyCover: Boolean
        get() = prefs.getBoolean("notify_cover", false)
        set(v) = prefs.edit().putBoolean("notify_cover", v).apply()

    /** Which teacher in this school the signed-in person is, if they chose one. */
    fun myTeacherId(schoolId: Int): Int? = prefs.getInt("me_$schoolId", -1).takeIf { it > 0 }
    fun setMyTeacherId(schoolId: Int, teacherId: Int?) = prefs.edit().putInt("me_$schoolId", teacherId ?: -1).apply()

    /** Cover already notified about, so each is announced once. */
    var notified: Set<String>
        get() = prefs.getStringSet("notified", emptySet()) ?: emptySet()
        set(v) = prefs.edit().putStringSet("notified", v.toList().takeLast(300).toSet()).apply()

    var userEmail: String?
        get() = prefs.getString("user_email", null)
        set(v) = prefs.edit().putString("user_email", v).apply()

    fun signOut() = prefs.edit().remove("token").remove("school_id").remove("user_email").apply()
}
