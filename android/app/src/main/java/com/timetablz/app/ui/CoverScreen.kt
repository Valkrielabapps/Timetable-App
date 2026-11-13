package com.timetablz.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.timetablz.app.data.ApiException
import com.timetablz.app.data.Cover
import com.timetablz.app.data.Dates
import com.timetablz.app.data.Lesson
import com.timetablz.app.data.SavedCover
import com.timetablz.app.data.Summary
import com.timetablz.app.ui.theme.Amber50
import com.timetablz.app.ui.theme.Amber800
import com.timetablz.app.ui.theme.Emerald50
import com.timetablz.app.ui.theme.Emerald700
import com.timetablz.app.ui.theme.Ink
import com.timetablz.app.ui.theme.Red600
import com.timetablz.app.ui.theme.Slate500
import kotlinx.coroutines.launch

private const val UNCOVERED = -1

/**
 * A day's cover. An admin marks who's away, each of their lessons gets the
 * best free teacher (changeable), then Save and Email teachers - the same as
 * the website's Substitutions screen, saved to the same place. A viewer sees
 * the day's arrangement.
 */
@Composable
fun CoverScreen(state: AppState, data: SchoolData) {
    val school = state.school ?: return
    val timetable = data.timetable
    if (timetable == null) {
        Message("No timetable yet", "Cover needs the school's timetable. Generate one on timetablz.com first.")
        return
    }
    // Saving or emailing finishes even if you switch tabs meanwhile.
    val scope = state.scope
    var date by rememberSaveable { mutableStateOf(Dates.today()) }
    var saved by remember { mutableStateOf<List<SavedCover>>(emptyList()) }
    var absent by remember { mutableStateOf<Set<Int>>(emptySet()) }
    var picks by remember { mutableStateOf<Map<String, Int?>>(emptyMap()) }
    var summary by remember { mutableStateOf<Summary?>(null) }
    var choosingAway by remember { mutableStateOf(false) }
    var choosingFor by remember { mutableStateOf<Lesson?>(null) }
    var busy by remember { mutableStateOf<String?>(null) }
    var note by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    val entries = timetable.entries
    val load = remember(timetable.id) { Cover.weeklyLoad(entries) }
    val dayLessons = remember(timetable.id, date) { Cover.lessonsOn(entries, Dates.weekday(date)) }
    val toCover = dayLessons.filter { it.teacherId in absent }
    val teachersToday = data.teachers.filter { t -> dayLessons.any { it.teacherId == t.id } }.sortedBy { it.name.lowercase() }

    // The school's saved cover, once.
    LaunchedEffect(school.id) {
        saved = runCatching { state.api.covers(school.id) }.getOrDefault(emptyList())
    }
    // A day that already has cover starts from it; another day starts empty.
    LaunchedEffect(date, saved) {
        val here = saved.firstOrNull { it.date == date && it.category == null }
        absent = here?.absentIds?.ifEmpty { here.changes.map { it.absentTeacherId }.toSet() } ?: emptySet()
        picks = if (here != null) Cover.picksFrom(here, dayLessons) else emptyMap()
        note = null
        error = null
        summary = if (here != null || !school.isAdmin) runCatching { state.api.summary(school.id, date) }.getOrNull() else null
    }
    // Every lesson that needs cover gets the top suggestion, unless already chosen.
    LaunchedEffect(absent, date) {
        picks = Cover.autofill(toCover, data.teachers, entries, absent, picks, load)
    }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = { date = Dates.add(date, -1) }) { Text("‹", color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.titleLarge) }
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(Dates.pretty(date), style = MaterialTheme.typography.titleMedium)
                    if (date == Dates.today()) Text("Today", style = MaterialTheme.typography.bodySmall, color = Slate500)
                }
                TextButton(onClick = { date = Dates.add(date, 1) }) { Text("›", color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.titleLarge) }
            }
            if (date != Dates.today()) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                    Pill("Back to today", false) { date = Dates.today() }
                }
            }
        }

        if (!school.isAdmin) {
            item { SummaryCard(summary, empty = "No cover arranged for this day.") }
            return@LazyColumn
        }

        if (dayLessons.isEmpty()) {
            item { Message("No lessons this day", "Pick a school day.") }
            return@LazyColumn
        }

        item {
            Text("Who's away?", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp))
            Spacer(Modifier.heightIn(min = 6.dp))
            if (absent.isEmpty()) {
                Text("Nobody yet.", color = Slate500)
            } else {
                Text(
                    data.teachers.filter { it.id in absent }.joinToString(", ") { it.name },
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
            SecondaryButton(
                if (absent.isEmpty()) "Mark teachers away" else "Change who's away",
                { choosingAway = true }, Modifier.fillMaxWidth().padding(top = 8.dp),
            )
        }

        if (toCover.isNotEmpty()) {
            item {
                Text(
                    "Cover · ${toCover.size} ${if (toCover.size == 1) "lesson" else "lessons"}",
                    style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 12.dp),
                )
            }
            items(toCover, key = { it.key }) { lesson ->
                val sub = picks[lesson.key]
                val subName = data.teachers.firstOrNull { it.id == sub }?.name
                Card(onClick = { choosingFor = lesson }) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        val period = data.periods.firstOrNull { it.id == lesson.periodId }
                        Text(
                            "${period?.short ?: ""} · ${lesson.classGroupNames.joinToString(", ")} · ${lesson.subjectName}",
                            style = MaterialTheme.typography.titleSmall,
                        )
                        Text("${lesson.teacherName} is away", style = MaterialTheme.typography.bodySmall, color = Slate500)
                        Row(
                            Modifier
                                .padding(top = 4.dp)
                                .background(if (subName != null) Emerald50 else Amber50, RoundedCornerShape(6.dp))
                                .padding(horizontal = 10.dp, vertical = 6.dp),
                        ) {
                            Text(
                                if (subName != null) "Covered by $subName  ▾" else "Not covered  ▾",
                                color = if (subName != null) Emerald700 else Amber800,
                                style = MaterialTheme.typography.labelLarge,
                            )
                        }
                    }
                }
            }
        }

        item {
            error?.let { Text(it, color = Red600, modifier = Modifier.padding(top = 8.dp)) }
            note?.let { Text(it, color = Emerald700, modifier = Modifier.padding(top = 8.dp)) }
            PrimaryButton(
                "Save cover", {
                    busy = "save"
                    error = null
                    scope.launch {
                        try {
                            state.api.saveCover(school.id, Cover.body(date, absent, toCover, picks))
                            saved = state.api.covers(school.id)
                            summary = state.api.summary(school.id, date)
                            note = "Saved. Teachers can see it on the website and in the app."
                        } catch (e: ApiException) {
                            error = e.message
                        } finally {
                            busy = null
                        }
                    }
                },
                Modifier.fillMaxWidth().padding(top = 12.dp),
                enabled = absent.isNotEmpty() || saved.any { it.date == date && it.category == null },
                busy = busy == "save",
            )
            val savedToday = saved.any { it.date == date && it.category == null }
            if (savedToday) {
                SecondaryButton(
                    if (busy == "email") "Sending…" else "Email teachers their cover",
                    {
                        busy = "email"
                        error = null
                        scope.launch {
                            try {
                                val r = state.api.notify(school.id, date, everyone = false)
                                note = when {
                                    !r.configured -> "Email isn't set up for Timetablz yet."
                                    r.sent.isEmpty() && r.noEmail.isEmpty() && r.failed.isEmpty() -> "Nobody needed an email."
                                    else -> buildString {
                                        if (r.sent.isNotEmpty()) append("Emailed ${r.sent.joinToString(", ")}. ")
                                        if (r.noEmail.isNotEmpty()) append("No email address for ${r.noEmail.joinToString(", ")}. ")
                                        if (r.failed.isNotEmpty()) append("Couldn't send to ${r.failed.joinToString(", ")}${r.reason?.let { ": $it" } ?: ""}.")
                                    }.trim()
                                }
                            } catch (e: ApiException) {
                                error = e.message
                            } finally {
                                busy = null
                            }
                        }
                    },
                    Modifier.fillMaxWidth().padding(top = 8.dp),
                    enabled = busy == null,
                )
            }
        }

        if (summary != null) {
            item { SummaryCard(summary, empty = "") }
        }
    }

    if (choosingAway) {
        AwayDialog(
            teachers = teachersToday.map { it.id to it.name },
            chosen = absent,
            onDone = { absent = it; choosingAway = false },
            onDismiss = { choosingAway = false },
        )
    }
    choosingFor?.let { lesson ->
        val ranked = Cover.rank(lesson, data.teachers, entries, absent, picks, toCover, load)
        val options = ranked.suggested.map { PickerOption(it.id, it.name, "${load[it.id] ?: 0} lessons a week", "Suggested: free and teaches ${lesson.subjectName}") } +
            ranked.others.map { PickerOption(it.id, it.name, "${load[it.id] ?: 0} lessons a week", "Also free") } +
            PickerOption(UNCOVERED, "Leave it uncovered", group = " ")
        PickerDialog(
            title = "Who covers ${lesson.subjectName}?",
            options = options,
            selected = picks[lesson.key] ?: UNCOVERED,
            onPick = { id -> picks = picks + (lesson.key to (if (id == UNCOVERED) null else id)); choosingFor = null },
            onDismiss = { choosingFor = null },
            searchable = options.size > 12,
        )
    }
}

@Composable
private fun AwayDialog(teachers: List<Pair<Int, String>>, chosen: Set<Int>, onDone: (Set<Int>) -> Unit, onDismiss: () -> Unit) {
    var picked by remember { mutableStateOf(chosen) }
    var query by remember { mutableStateOf("") }
    val shown = teachers.filter { query.isBlank() || it.second.contains(query.trim(), ignoreCase = true) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Who's away all day?", style = MaterialTheme.typography.titleMedium) },
        text = {
            Column {
                OutlinedTextField(query, { query = it }, singleLine = true, placeholder = { Text("Search") },
                    modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
                LazyColumn(Modifier.heightIn(max = 400.dp)) {
                    items(shown, key = { it.first }) { (id, name) ->
                        Row(
                            Modifier.fillMaxWidth().clickable { picked = if (id in picked) picked - id else picked + id }.padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Checkbox(
                                checked = id in picked,
                                onCheckedChange = { picked = if (it) picked + id else picked - id },
                                colors = CheckboxDefaults.colors(checkedColor = MaterialTheme.colorScheme.primary),
                            )
                            Text(name, modifier = Modifier.width(220.dp), fontWeight = if (id in picked) FontWeight.SemiBold else FontWeight.Normal)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { onDone(picked) }) { Text("Done", color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.SemiBold) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = Slate500) } },
    )
}

@Composable
private fun SummaryCard(summary: Summary?, empty: String) {
    if (summary == null || (summary.rows.isEmpty() && summary.onLeave.isEmpty())) {
        if (empty.isNotEmpty()) Message("Nothing arranged", empty)
        return
    }
    Card {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("The day's arrangement", style = MaterialTheme.typography.titleMedium)
            if (summary.onLeave.isNotEmpty()) {
                Text("Away: ${summary.onLeave.joinToString(", ")}", color = Slate500, style = MaterialTheme.typography.bodyMedium)
            }
            summary.rows.forEach { r ->
                Row(Modifier.fillMaxWidth().padding(top = 4.dp)) {
                    Text(r.period, modifier = Modifier.width(48.dp), style = MaterialTheme.typography.labelLarge)
                    Column(Modifier.weight(1f)) {
                        Text("${r.classGroup}${r.subject?.let { " · $it" } ?: ""}", style = MaterialTheme.typography.bodyMedium)
                        Text(
                            r.substitute?.let { "$it for ${r.absent}" } ?: "Not covered (${r.absent} away)",
                            style = MaterialTheme.typography.bodySmall,
                            color = if (r.substitute != null) Slate500 else Amber800,
                        )
                    }
                }
            }
            if (summary.uncovered > 0) {
                Text("${summary.uncovered} not covered", color = Amber800, style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}
