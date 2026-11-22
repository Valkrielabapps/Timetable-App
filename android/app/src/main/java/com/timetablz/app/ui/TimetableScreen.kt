package com.timetablz.app.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.core.FastOutLinearInEasing
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.timetablz.app.data.Dates
import com.timetablz.app.data.SchoolData
import com.timetablz.app.data.Entry
import com.timetablz.app.data.Natural
import com.timetablz.app.data.Period
import com.timetablz.app.data.Timetable
import com.timetablz.app.data.WeekCells
import com.timetablz.app.data.WeekLayout
import kotlinx.coroutines.launch
import com.timetablz.app.ui.theme.Slate500

/**
 * Timetables. My timetable is one teacher's day, one period under another (the
 * phone-sized version of the website's grid), or their whole week in one frame.
 * Teachers' and Classes' timetables are every teacher's or section's week, one
 * under another to scroll through, as on the website, with a picker to jump.
 */
@Composable
fun TimetableScreen(data: SchoolData, mode: String, fixedTeacherId: Int? = null, vm: TimetableViewModel = viewModel(factory = AppViewModels.Factory)) {
    val timetable = data.timetable
    if (timetable == null || timetable.entries.isEmpty()) {
        Message("No timetable yet", "Generate one on rivelletimetables.com and it shows here.")
        return
    }
    // Worked out once per data change, not on every redraw.
    val layout = remember(data.periods) { WeekLayout(data.periods) }
    val today = Dates.weekday(Dates.today()).takeIf { it in layout.days }
    if (mode == "mine" && fixedTeacherId != null) MyTimetable(data, timetable, layout, today, fixedTeacherId, vm)
    else EveryWeek(data, timetable, layout, today, sections = mode == "section")
}

@Composable
private fun MyTimetable(data: SchoolData, timetable: Timetable, layout: WeekLayout, today: Int?, teacherId: Int, vm: TimetableViewModel) {
    val week by vm.week.collectAsStateWithLifecycle()
    val chosenDay by vm.day.collectAsStateWithLifecycle()
    val day = chosenDay ?: today ?: layout.days.firstOrNull() ?: 0

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    data.teachers.firstOrNull { it.id == teacherId }?.name ?: "",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Pill("Day", !week) { vm.week.value = false }
                    Pill("Week", week) { vm.week.value = true }
                }
            }
            if (!week) {
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    layout.days.forEach { d -> Pill(Dates.dayShort[d], d == day) { vm.day.value = d } }
                }
            }
        }
        Crossfade(targetState = week, animationSpec = tween(200), label = "day or week") { showWeek ->
            if (showWeek) {
                val cells = remember(timetable, teacherId) { WeekCells.forTeacher(timetable.entries, teacherId) }
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 16.dp, end = 16.dp, bottom = 24.dp)) {
                    WeekGrid(layout, cells, today)
                }
            } else {
                DayList(data, timetable, day, teacherId)
            }
        }
    }
}

@Composable
private fun DayList(data: SchoolData, timetable: Timetable, day: Int, teacherId: Int) {
    // Changing day slides the new day in.
    AnimatedContent(
        targetState = day,
        transitionSpec = {
            val forward = targetState >= initialState
            // The same shared-axis motion as the pages: old day out first, new day in after.
            (fadeIn(tween(210, delayMillis = 90, easing = LinearOutSlowInEasing)) +
                slideInHorizontally(tween(300, easing = FastOutSlowInEasing)) { if (forward) it / 12 else -it / 12 }) togetherWith
                (fadeOut(tween(90, easing = FastOutLinearInEasing)) +
                    slideOutHorizontally(tween(300, easing = FastOutSlowInEasing)) { if (forward) -it / 12 else it / 12 })
        },
        label = "day",
    ) { d ->
        // Each day's list is built from its own day, so the one sliding out stays as it was.
        val dayPeriods = remember(data.periods, d) { data.periods.filter { it.day == d }.sortedBy { it.order } }
        val byPeriod = remember(timetable, d, teacherId) {
            timetable.entries.filter { it.day == d && it.teacherId == teacherId }.groupBy { it.periodId }
        }
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(dayPeriods, key = { it.id }) { p -> PeriodRow(p, byPeriod[p.id] ?: emptyList(), "teacher") }
        }
    }
}

/** Every teacher's (or section's) week, one under another, in the website's order. */
@Composable
private fun EveryWeek(data: SchoolData, timetable: Timetable, layout: WeekLayout, today: Int?, sections: Boolean) {
    val people = remember(timetable, data.teachers, sections) {
        if (sections) {
            timetable.entries.map { it.classGroupId to it.classGroupName }.distinct().sortedWith { a, b -> Natural.compare(a.second, b.second) }
        } else {
            val teaching = timetable.entries.mapNotNull { it.teacherId }.toSet()
            data.teachers.filter { it.id in teaching }.sortedBy { it.name.lowercase() }.map { it.id to it.name }
        }
    }
    val cells = remember(timetable, sections) {
        if (sections) WeekCells.forEverySection(timetable.entries) else WeekCells.forEveryTeacher(timetable.entries)
    }
    val list = rememberLazyListState()
    val scope = rememberCoroutineScope()
    // The picker names whoever is at the top of the list.
    val shown by remember(people) { derivedStateOf { people.getOrNull(list.firstVisibleItemIndex) } }
    var picking by remember { mutableStateOf(false) }
    val title = if (sections) "Jump to a section" else "Jump to a teacher"

    Column(Modifier.fillMaxSize()) {
        PickerField(title, shown?.second ?: "Choose", { picking = true }, Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
        LazyColumn(
            Modifier.fillMaxSize(),
            state = list,
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            items(people, key = { it.first }) { (id, name) ->
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(name, style = MaterialTheme.typography.titleSmall)
                    WeekGrid(layout, cells[id] ?: emptyMap(), today)
                }
            }
        }
    }

    if (picking) {
        PickerDialog(
            title,
            people.map { PickerOption(it.first, it.second) },
            shown?.first,
            onPick = { id ->
                picking = false
                val index = people.indexOfFirst { it.first == id }
                if (index >= 0) scope.launch { list.scrollToItem(index) }
            },
            onDismiss = { picking = false },
        )
    }
}

@Composable
private fun PeriodRow(p: Period, entries: List<Entry>, view: String) {
    if (!p.isLesson) {
        // Breaks and the like: a thin grey band.
        Row(
            Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, Rounded).padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(p.label ?: "Break", style = MaterialTheme.typography.bodySmall, color = Slate500)
        }
        return
    }
    Card {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.width(52.dp)) {
                Text(p.short, style = MaterialTheme.typography.titleMedium)
                p.label?.takeIf { it != p.short && !it.startsWith("Period") }?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall, color = Slate500)
                }
            }
            if (entries.isEmpty()) {
                Text("Free", color = Slate500)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    val block = entries.firstNotNullOfOrNull { it.blockName }
                    if (block != null && view == "section") {
                        Text(block, style = MaterialTheme.typography.titleSmall)
                        entries.forEach { e ->
                            Text("${e.subjectName} · ${e.teacherName ?: "No teacher yet"}", style = MaterialTheme.typography.bodySmall, color = Slate500)
                        }
                    } else {
                        val e = entries.first()
                        Text(e.subjectName, style = MaterialTheme.typography.titleSmall)
                        val who = if (view == "section") e.teacherName ?: "No teacher yet"
                        else entries.map { it.classGroupName }.distinct().joinToString(", ")
                        Text(listOfNotNull(who, e.roomName).joinToString(" · "), style = MaterialTheme.typography.bodySmall, color = Slate500)
                    }
                }
            }
        }
    }
}
