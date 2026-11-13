package com.timetablz.app.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.timetablz.app.data.CoverWorker

/** Settings: theme, who I am, notifications, calendar, account. */
@Composable
fun SettingsScreen(state: AppState) {
    val context = LocalContext.current
    val school = state.school ?: return
    var pickingMe by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf<String?>(null) }
    val me = state.me()

    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            state.setNotify(true)
            CoverWorker.schedule(context)
        } else {
            note = "Notifications are blocked for Timetablz. Turn them on in your phone's Settings → Apps → Timetablz."
        }
    }

    fun turnNotifications(on: Boolean) {
        note = null
        if (!on) {
            state.setNotify(false)
            CoverWorker.cancel(context)
        } else if (Build.VERSION.SDK_INT >= 33 && !CoverWorker.canNotify(context)) {
            askPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            state.setNotify(true)
            CoverWorker.schedule(context)
        }
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Settings", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 8.dp, bottom = 4.dp))

        Section("Theme") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Pill("Same as phone", state.theme == "system") { state.chooseTheme("system") }
                Pill("Light", state.theme == "light") { state.chooseTheme("light") }
                Pill("Dark", state.theme == "dark") { state.chooseTheme("dark") }
            }
        }

        Section("I am", "So My timetable and My substitutions show your lessons.") {
            PickerField("Teacher", me?.name ?: "Choose yourself", { pickingMe = true })
            if (me != null && state.chosenMe == null) {
                Text("Matched by your email.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        Section("Notifications") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Tell me when I'm given cover", style = MaterialTheme.typography.bodyLarge)
                    Text("Checked about every half hour, even with the app closed.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(
                    checked = state.notifyCover,
                    onCheckedChange = { turnNotifications(it) },
                    colors = SwitchDefaults.colors(checkedTrackColor = MaterialTheme.colorScheme.primary),
                )
            }
            if (state.notifyCover && me == null) {
                Text("Choose yourself under I am first, so we know which cover is yours.", color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall)
            }
            note?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        }

        Section("Google Calendar") {
            Text(
                "Each lesson on the Substitution page has a calendar button: tap it to add the lesson to Google Calendar, " +
                    "at its period's time if your school has period times set.\n\nThe cover emails your school sends also " +
                    "carry a calendar invite: open one in Gmail and tap Yes, and changes and cancellations update your " +
                    "calendar by themselves.",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (me?.email.isNullOrBlank()) {
                Text("Ask your school to add your email to your teacher record so the invites reach you.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                Text("Invites go to ${me?.email}.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        Section("Account") {
            Text(state.user?.email ?: "", style = MaterialTheme.typography.bodyLarge)
            Text("${school.name} · ${if (school.isAdmin) "Admin" else "Viewer"}", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (state.schools.size > 1) SecondaryButton("Switch school", { state.switchSchool() }, Modifier.fillMaxWidth())
            SecondaryButton("Sign out", {
                CoverWorker.cancel(context)
                state.setNotify(false)
                state.signOut()
            }, Modifier.fillMaxWidth())
        }
    }

    if (pickingMe) {
        val options = state.data?.teachers?.sortedBy { it.name.lowercase() }?.map { PickerOption(it.id, it.name, it.email) } ?: emptyList()
        PickerDialog("Which teacher are you?", options, me?.id,
            onPick = { state.chooseMe(it); pickingMe = false }, onDismiss = { pickingMe = false })
    }
}

@Composable
private fun Section(title: String, about: String? = null, content: @Composable () -> Unit) {
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            about?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            content()
        }
    }
}
