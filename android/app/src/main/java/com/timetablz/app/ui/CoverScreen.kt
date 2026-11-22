package com.timetablz.app.ui

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.timetablz.app.data.Cover
import com.timetablz.app.data.Dates
import com.timetablz.app.data.Lesson
import com.timetablz.app.data.Period
import com.timetablz.app.data.SchoolData
import com.timetablz.app.data.Summary
import com.timetablz.app.ui.theme.Amber50
import com.timetablz.app.ui.theme.Amber800
import com.timetablz.app.ui.theme.Emerald50
import com.timetablz.app.ui.theme.Emerald700
import com.timetablz.app.ui.theme.Slate500

private const val UNCOVERED = -1

/**
 * A day's cover, in the website's steps: the date, which part of the school,
 * who's away (all day or some periods), then a substitute for each lesson -
 * suggested (teaches the subject, in this part), free in this part, or free
 * in another part. Save, Email and Share work on that part, saved to the
 * same place as the website. A viewer sees the arrangement for a part.
 */
@Composable
fun CoverScreen(session: SessionViewModel, data: SchoolData, vm: CoverViewModel = viewModel(factory = AppViewModels.Factory)) {
    val sessionUi by session.ui.collectAsStateWithLifecycle()
    val school = sessionUi.school ?: return
    val timetable = data.timetable
    if (timetable == null) {
        Message("No timetable yet", "Cover needs the school's timetable. Generate one on rivelletimetables.com first.")
        return
    }
    LaunchedEffect(school.id, data) { vm.bind(school.id, school.isAdmin, data) }
    val ui by vm.ui.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var choosingAway by remember { mutableStateOf(false) }
    var choosingFor by remember { mutableStateOf<Lesson?>(null) }

    // Worked out when the day, part, who's away or the data change - not on every redraw.
    val partOf = remember(data) { data.partOfSection() }
    val dayLessons = remember(data, ui.date, ui.part) {
        ui.part?.let { Cover.lessonsOn(data.timetable?.entries ?: emptyList(), Dates.weekday(ui.date), it, partOf) } ?: emptyList()
    }
    val toCover = remember(dayLessons, ui.absences) { dayLessons.filter { Cover.isAway(ui.absences, it.teacherId, it.periodId) } }
    val periodsById = remember(data.periods) { data.periods.associateBy { it.id } }
    val teachersById = remember(data.teachers) { data.teachers.associateBy { it.id } }
    // Teachers with lessons in this part that day, and the periods of those lessons.
    val teachersToday = remember(dayLessons, data.teachers) {
        val periods = dayLessons.groupBy({ it.teacherId }, { it.periodId })
        data.teachers.filter { it.id in periods }.sortedBy { it.name.lowercase() }.map { t ->
            AwayChoice(t.id, t.name, periods[t.id].orEmpty().distinct().mapNotNull { periodsById[it] }.sortedBy { it.order })
        }
    }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        // 1. Date
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = { vm.setDate(Dates.add(ui.date, -1)) }) {
                    Text("‹", color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.titleLarge)
                }
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(Dates.pretty(ui.date), style = MaterialTheme.typography.titleMedium)
                    if (ui.date == Dates.today()) Text("Today", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                TextButton(onClick = { vm.setDate(Dates.add(ui.date, 1)) }) {
                    Text("›", color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.titleLarge)
                }
            }
            if (ui.date != Dates.today()) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                    Pill("Back to today", false) { vm.setDate(Dates.today()) }
                }
            }
        }

        // 2. Which part of the school?
        item {
            Text("Which part of the school?", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 4.dp))
            Row(
                Modifier.horizontalScroll(rememberScrollState()).padding(top = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                (listOf(Cover.WHOLE) + Cover.PARTS.map { it.first }).forEach { key ->
                    Pill(Cover.partLabel(key), ui.part == key || (!school.isAdmin && ui.part == null && key == Cover.WHOLE)) { vm.setPart(key) }
                }
            }
        }

        if (!school.isAdmin) {
            item { SummaryCard(ui.summary, empty = "No cover arranged for this day.", onShare = { share(context, it) }) }
            return@LazyColumn
        }
        if (ui.part == null) {
            item { Text("Pick a part of the school to arrange its cover.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
            return@LazyColumn
        }
        val partName = Cover.partLabel(ui.part).lowercase()
        if (dayLessons.isEmpty()) {
            item { Message("No lessons", "No lessons in ${partName} this day. Pick another day or part of the school.") }
            return@LazyColumn
        }

        // 3. Who's away?
        item {
            Text("Who's away?", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp))
            Spacer(Modifier.heightIn(min = 6.dp))
            val away = teachersToday.filter { it.id in ui.absences }
            if (away.isEmpty()) {
                Text("Nobody yet.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                away.forEach { t ->
                    val ids = ui.absences[t.id]
                    val how = when {
                        ids == null -> "whole day"
                        ids.isEmpty() -> "no periods ticked"
                        else -> t.periods.filter { it.id in ids }.joinToString(", ") { it.short }
                    }
                    Text("${t.name} ($how)", style = MaterialTheme.typography.bodyLarge)
                }
            }
            SecondaryButton(
                if (away.isEmpty()) "Mark teachers away" else "Change who's away",
                { choosingAway = true }, Modifier.fillMaxWidth().padding(top = 8.dp),
            )
        }

        // 4. Substitutes
        if (toCover.isNotEmpty()) {
            item {
                Text("Substitutes · ${toCover.size} ${if (toCover.size == 1) "lesson" else "lessons"}",
                    style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 12.dp))
            }
            items(toCover, key = { it.key }) { lesson ->
                val subId = ui.picks[lesson.key]
                val subName = subId?.let { teachersById[it]?.name }
                Card(onClick = { choosingFor = lesson }) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        val period = periodsById[lesson.periodId]
                        Text("${period?.short ?: ""} · ${lesson.classGroupNames.joinToString(", ")} · ${lesson.subjectName}",
                            style = MaterialTheme.typography.titleSmall)
                        Text("${lesson.teacherName} is away", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
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
                        if (subId != null) {
                            Text(vm.loadText(subId, lesson.key), style = MaterialTheme.typography.bodySmall, color = Slate500)
                        }
                    }
                }
            }
        } else if (ui.absences.isNotEmpty()) {
            item { Text("No lessons need cover for the periods chosen.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }

        item {
            ui.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp)) }
            ui.note?.let { Text(it, color = MaterialTheme.colorScheme.tertiary, modifier = Modifier.padding(top = 8.dp)) }
            PrimaryButton(
                "Save cover for $partName", { vm.save() }, Modifier.fillMaxWidth().padding(top = 12.dp),
                enabled = ui.absences.isNotEmpty() || ui.savedToday, busy = ui.busy == "save",
            )
            if (ui.savedToday) {
                SecondaryButton(
                    if (ui.busy == "email") "Sending…" else "Email teachers their cover",
                    { vm.email() }, Modifier.fillMaxWidth().padding(top = 8.dp), enabled = ui.busy == null,
                )
            }
        }

        if (ui.summary != null) item { SummaryCard(ui.summary, empty = "", onShare = { share(context, it) }) }
    }

    if (choosingAway) {
        AwayDialog(
            teachers = teachersToday,
            chosen = ui.absences,
            onDone = { vm.setAbsences(it); choosingAway = false },
            onDismiss = { choosingAway = false },
        )
    }
    choosingFor?.let { lesson ->
        val ranked = vm.rank(lesson)
        val here = lesson.part?.let { Cover.partLabel(it).lowercase() } ?: "this part"
        fun opt(t: com.timetablz.app.data.Teacher, group: String) = PickerOption(t.id, t.name, vm.loadText(t.id, lesson.key), group)
        val options = ranked.suggested.map { opt(it, "Suggested: free, teaches ${lesson.subjectName}, in $here") } +
            ranked.same.map { opt(it, "Free in $here") } +
            ranked.elsewhere.map { opt(it, "Free in other parts of the school") } +
            PickerOption(UNCOVERED, "Leave it uncovered", group = " ")
        PickerDialog(
            title = "Who covers ${lesson.subjectName}?",
            options = options,
            selected = ui.picks[lesson.key] ?: UNCOVERED,
            onPick = { id -> vm.pick(lesson.key, if (id == UNCOVERED) null else id); choosingFor = null },
            onDismiss = { choosingFor = null },
            searchable = options.size > 12,
        )
    }
}

/** Sends the summary to WhatsApp or anywhere else that takes text. */
private fun share(context: Context, summary: Summary) {
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, Cover.summaryText(summary))
    }
    context.startActivity(Intent.createChooser(send, "Share substitutions"))
}

/** A teacher who could be marked away, with their lessons' periods that day. */
private data class AwayChoice(val id: Int, val name: String, val periods: List<Period>)

@Composable
private fun AwayDialog(
    teachers: List<AwayChoice>,
    chosen: Map<Int, Set<Int>?>,
    onDone: (Map<Int, Set<Int>?>) -> Unit,
    onDismiss: () -> Unit,
) {
    // Only teachers with lessons here today can be chosen; anyone else drops out.
    var picked by remember { mutableStateOf(chosen.filterKeys { id -> teachers.any { it.id == id } }) }
    var query by remember { mutableStateOf("") }
    val shown = teachers.filter { query.isBlank() || it.name.contains(query.trim(), ignoreCase = true) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Who's away?", style = MaterialTheme.typography.titleMedium) },
        text = {
            Column {
                OutlinedTextField(query, { query = it }, singleLine = true, placeholder = { Text("Search teachers") },
                    modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
                LazyColumn(Modifier.heightIn(max = 420.dp)) {
                    items(shown, key = { it.id }) { t ->
                        val isAway = t.id in picked
                        Column(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                            Row(
                                Modifier.fillMaxWidth().clickable { picked = if (isAway) picked - t.id else picked + (t.id to null) },
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Checkbox(
                                    checked = isAway,
                                    onCheckedChange = { picked = if (it) picked + (t.id to null) else picked - t.id },
                                    colors = CheckboxDefaults.colors(checkedColor = MaterialTheme.colorScheme.primary),
                                )
                                Text(t.name, modifier = Modifier.width(220.dp), fontWeight = if (isAway) FontWeight.SemiBold else FontWeight.Normal)
                            }
                            if (isAway) {
                                val ids = picked[t.id]
                                Row(Modifier.padding(start = 48.dp, bottom = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Pill("Whole day", ids == null) { picked = picked + (t.id to null) }
                                    Pill("Some periods", ids != null) { if (ids == null) picked = picked + (t.id to emptySet()) }
                                }
                                if (ids != null) {
                                    Row(
                                        Modifier.padding(start = 48.dp, bottom = 6.dp).horizontalScroll(rememberScrollState()),
                                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                                    ) {
                                        t.periods.forEach { p ->
                                            Pill(p.short, p.id in ids) {
                                                picked = picked + (t.id to (if (p.id in ids) ids - p.id else ids + p.id))
                                            }
                                        }
                                    }
                                }
                            }
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
private fun SummaryCard(summary: Summary?, empty: String, onShare: (Summary) -> Unit) {
    if (summary == null || (summary.rows.isEmpty() && summary.onLeave.isEmpty())) {
        if (empty.isNotEmpty()) Message("Nothing arranged", empty)
        return
    }
    Card {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("The day's arrangement · ${summary.partLabel}", style = MaterialTheme.typography.titleMedium)
            if (summary.onLeave.isNotEmpty()) {
                Text("On leave: ${summary.onLeave.joinToString(", ") { it.text }}", color = Slate500, style = MaterialTheme.typography.bodyMedium)
            }
            // The whole school's rows come grouped by part, as on the website.
            var lastPart: String? = "\u0000"
            summary.rows.forEach { r ->
                if (summary.part == null && r.partLabel.isNotBlank() && r.partLabel != lastPart) {
                    lastPart = r.partLabel
                    Text(r.partLabel, style = MaterialTheme.typography.labelMedium, color = Slate500, modifier = Modifier.padding(top = 6.dp))
                }
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
            SecondaryButton("Share (WhatsApp)", { onShare(summary) }, Modifier.fillMaxWidth().padding(top = 6.dp))
        }
    }
}
