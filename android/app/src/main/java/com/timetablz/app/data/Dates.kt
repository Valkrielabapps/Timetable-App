package com.timetablz.app.data

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/** Dates as the API writes them ("2026-11-13"), without java.time (needs Android 8). */
object Dates {
    private fun iso() = SimpleDateFormat("yyyy-MM-dd", Locale.US)

    fun today(): String = iso().format(Calendar.getInstance().time)

    fun add(date: String, days: Int): String {
        val c = Calendar.getInstance().apply { time = iso().parse(date)!!; add(Calendar.DAY_OF_MONTH, days) }
        return iso().format(c.time)
    }

    /** 0 = Monday ... 6 = Sunday, as the timetable counts days. */
    fun weekday(date: String): Int {
        val c = Calendar.getInstance().apply { time = iso().parse(date)!! }
        return (c.get(Calendar.DAY_OF_WEEK) + 5) % 7
    }

    /** "Friday, 13 Nov". */
    fun pretty(date: String): String =
        SimpleDateFormat("EEEE, d MMM", Locale.getDefault()).format(iso().parse(date)!!)

    val dayShort = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
}
