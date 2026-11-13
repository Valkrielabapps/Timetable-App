package com.timetablz.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.timetablz.app.data.ApiException
import com.timetablz.app.data.CalendarLink
import com.timetablz.app.data.Dates
import com.timetablz.app.data.MyCover
import com.timetablz.app.data.MyCoverItem
import com.timetablz.app.data.SavedCover

/**
 * My substitutions: the lessons I've been given to cover - today, coming up,
 * and the last two weeks - as Period · Grade · Subject, each with "add to
 * calendar".
 */
@Composable
fun MySubstitutionsScreen(state: AppState, data: SchoolData, onOpenSettings: () -> Unit) {
    val school = state.school ?: return
    val context = LocalContext.current
    val me = state.me()
    var covers by remember { mutableStateOf<List<SavedCover>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(school.id, data) {
        error = null
        covers = try { state.api.covers(school.id) } catch (e: ApiException) { error = e.message; emptyList() }
    }

    if (me == null) {
        Message(
            "Which teacher are you?",
            "Your account's email isn't on a teacher here. Choose yourself in Settings → I am, and your substitutions show here.",
            "Open Settings", onOpenSettings,
        )
        return
    }
    val loaded = covers ?: run { Loading("Loading your substitutions…"); return }
    val entries = data.timetable?.entries ?: emptyList()
    val subjects = entries.associate { it.subjectId to it.subjectName }
    val all = MyCover.of(me.id, loaded, data.periods, entries, data.teachers, subjects)
    val today = Dates.today()
    val earliest = Dates.add(today, -14)
    val groups = listOf(
        "Today" to all.filter { it.date == today },
        "Coming up" to all.filter { it.date > today },
        "Earlier" to all.filter { it.date < today && it.date >= earliest }.reversed(),
    ).filter { it.second.isNotEmpty() }
    val periodLabels = data.periods.associate { it.id to it.label }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            Text("My substitutions", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 8.dp))
            Text(me.name, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp)) }
        }
        if (groups.isEmpty()) {
            item { Message("No substitutions", "When you're given a lesson to cover, it shows here.") }
        }
        groups.forEach { (title, list) ->
            item {
                Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 16.dp, bottom = 4.dp))
                Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp)) {
                    Header("Period", Modifier.width(64.dp))
                    Header("Grade", Modifier.weight(1f))
                    Header("Subject", Modifier.weight(1.2f))
                    Header("", Modifier.width(40.dp))
                }
                HorizontalDivider()
            }
            items(list, key = { it.key }) { item ->
                CoverRow(item, showDate = title != "Today") {
                    CalendarLink.add(context, item, periodLabels[item.periodId], school.name)
                }
            }
        }
    }
}

@Composable
private fun Header(text: String, modifier: Modifier) {
    Text(text, modifier = modifier.padding(vertical = 6.dp), style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.SemiBold)
}

@Composable
private fun CoverRow(item: MyCoverItem, showDate: Boolean, onCalendar: () -> Unit) {
    Column {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(item.periodLabel, Modifier.width(64.dp), style = MaterialTheme.typography.titleMedium)
            Text(item.classGroup, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
            Column(Modifier.weight(1.2f)) {
                Text(item.subject.ifEmpty { "-" }, style = MaterialTheme.typography.bodyLarge)
                Text(
                    listOfNotNull(if (showDate) Dates.pretty(item.date) else null, "for ${item.forTeacher}").joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            IconButton(onClick = onCalendar, modifier = Modifier.width(40.dp)) {
                Icon(Icons.Default.DateRange, contentDescription = "Add to calendar")
            }
        }
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    }
}
