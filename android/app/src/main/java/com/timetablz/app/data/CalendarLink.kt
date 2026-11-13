package com.timetablz.app.data

import android.content.Context
import android.content.Intent
import android.provider.CalendarContract
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/**
 * Adds a cover lesson to the phone's calendar (Google Calendar, or whichever
 * the person uses): opens it with the event filled in, for them to save. With
 * period times in the school's period labels ("9:00-9:45") it's at that time;
 * otherwise an all-day reminder for the date.
 */
object CalendarLink {
    fun add(context: Context, item: MyCoverItem, periodLabel: String?, school: String) {
        val day = SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(item.date) ?: return
        val times = MyCover.times(periodLabel)
        val intent = Intent(Intent.ACTION_INSERT).apply {
            data = CalendarContract.Events.CONTENT_URI
            putExtra(CalendarContract.Events.TITLE, "Cover: ${item.classGroup} ${item.subject}".trim())
            putExtra(CalendarContract.Events.DESCRIPTION,
                "${item.periodLabel} at $school, covering for ${item.forTeacher}. From Timetablz.")
            putExtra(CalendarContract.Events.EVENT_LOCATION, school)
            if (times != null) {
                fun at(h: Int, m: Int) = Calendar.getInstance().apply {
                    time = day; set(Calendar.HOUR_OF_DAY, h); set(Calendar.MINUTE, m); set(Calendar.SECOND, 0)
                }.timeInMillis
                putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, at(times.first.first, times.first.second))
                putExtra(CalendarContract.EXTRA_EVENT_END_TIME, at(times.second.first, times.second.second))
            } else {
                putExtra(CalendarContract.EXTRA_EVENT_ALL_DAY, true)
                putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, day.time)
                putExtra(CalendarContract.EXTRA_EVENT_END_TIME, day.time + 24L * 60 * 60 * 1000)
            }
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }
}
