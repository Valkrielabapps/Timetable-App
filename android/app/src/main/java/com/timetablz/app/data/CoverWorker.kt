package com.timetablz.app.data

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.timetablz.app.MainActivity
import com.timetablz.app.R
import java.util.concurrent.TimeUnit

/**
 * Every half hour or so, while notifications are on: has the signed-in
 * teacher been given new cover today or later? Each new lesson is announced
 * once ("You're covering 7 A Maths in P2 today"). Runs in the background
 * through WorkManager, so it works with the app closed; no Firebase needed.
 */
class CoverWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    companion object {
        private const val WORK = "cover-check"
        private const val CHANNEL = "cover"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<CoverWorker>(30, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(WORK, ExistingPeriodicWorkPolicy.KEEP, request)
        }

        fun cancel(context: Context) = WorkManager.getInstance(context).cancelUniqueWork(WORK)

        fun canNotify(context: Context) = Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

        private fun channel(context: Context) {
            if (Build.VERSION.SDK_INT >= 26) {
                val nm = context.getSystemService(NotificationManager::class.java)
                nm.createNotificationChannel(
                    NotificationChannel(CHANNEL, "Cover", NotificationManager.IMPORTANCE_HIGH).apply {
                        description = "When you're given a lesson to cover"
                    }
                )
            }
        }
    }

    override suspend fun doWork(): Result {
        val session = Session(applicationContext)
        val token = session.token ?: return Result.success()
        val schoolId = session.schoolId ?: return Result.success()
        if (!session.notifyCover || !canNotify(applicationContext)) return Result.success()
        return try {
            val api = Api(token = token)
            val teachers = api.teachers(schoolId)
            val me = MyCover.whoAmI(teachers, session.userEmail, session.myTeacherId(schoolId)) ?: return Result.success()
            val periods = api.periods(schoolId)
            val timetable = api.currentTimetable(schoolId)
            val entries = timetable?.entries ?: emptyList()
            val subjects = entries.associate { it.subjectId to it.subjectName }
            val today = Dates.today()
            val mine = MyCover.of(me.id, api.covers(schoolId), periods, entries, teachers, subjects).filter { it.date >= today }
            val seen = session.notified
            val fresh = mine.filter { it.key !in seen }
            if (fresh.isNotEmpty()) {
                notify(fresh, today)
                session.notified = seen + fresh.map { it.key }
            }
            Result.success()
        } catch (e: ApiException) {
            if (e.status == 401) Result.success() else Result.retry()
        }
    }

    private fun notify(items: List<MyCoverItem>, today: String) {
        val ctx = applicationContext
        channel(ctx)
        val open = PendingIntent.getActivity(
            ctx, 0, Intent(ctx, MainActivity::class.java).putExtra("open", "substitution"),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val lines = items.map {
            val day = if (it.date == today) "today" else Dates.pretty(it.date)
            "${it.periodLabel} ${it.classGroup} ${it.subject}, $day".replace("  ", " ")
        }
        val title = if (items.size == 1) "You're covering ${items[0].classGroup} ${items[0].subject}".trim()
        else "You're covering ${items.size} lessons"
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(lines.first())
            .setStyle(NotificationCompat.InboxStyle().also { s -> lines.take(6).forEach { s.addLine(it) } })
            .setContentIntent(open)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        if (canNotify(ctx)) {
            @Suppress("MissingPermission")
            NotificationManagerCompat.from(ctx).notify(4201, n)
        }
    }
}
