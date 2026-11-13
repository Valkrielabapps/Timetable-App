package com.timetablz.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * The home page: what you can open. Make substitutions only for a school's
 * admins; the rest for everyone.
 */
@Composable
fun MenuScreen(state: AppState, onOpen: (Page) -> Unit) {
    val school = state.school ?: return
    val me = state.me()
    val items = buildList {
        if (school.isAdmin) add(Triple(Page.MakeCover, "Mark who's away and choose who covers", "Admin"))
        add(Triple(Page.MyTimetable, me?.let { "Your week, as ${it.name}" } ?: "Your own week", null))
        add(Triple(Page.TeacherTimetables, "Any teacher's week", null))
        add(Triple(Page.ClassTimetables, "Any section's week", null))
    }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            state.user?.name?.takeIf { it.isNotBlank() }?.let { "Hello, ${it.substringBefore(' ')}" } ?: "Menu",
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.padding(top = 8.dp, bottom = 8.dp),
        )
        items.forEachIndexed { i, (page, about, badge) ->
            Card(onClick = { onOpen(page) }) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("${i + 1}", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.width(28.dp))
                    Column(Modifier.weight(1f)) {
                        Text(page.title, style = MaterialTheme.typography.titleMedium)
                        Text(about, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    badge?.let { Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    Text("  ›", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
