package com.timetablz.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
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
import com.timetablz.app.ui.theme.Slate50
import com.timetablz.app.ui.theme.Slate500

/**
 * A section's or a teacher's day, one period under another - the phone-sized
 * version of the website's grid. Opens on today (or Monday at the weekend).
 */
@Composable
fun TimetableScreen(data: SchoolData, mode: String, fixedTeacherId: Int? = null, vm: TimetableViewModel = viewModel(factory = AppViewModels.Factory)) {
    val timetable = data.timetable
    if (timetable == null || timetable.entries.isEmpty()) {
        Message("No timetable yet", "Generate one on timetablz.com and it shows here.")
        return
    }
    // "mine" and "teacher" show a teacher's week; "section" a section's.
    val view = if (mode == "section") "section" else "teacher"
    val days = data.periods.map { it.day }.distinct().sorted()
    val today = Dates.weekday(Dates.today())
    val chosenDay by vm.day.collectAsStateWithLifecycle()
    val day = chosenDay ?: if (today in days) today else days.firstOrNull() ?: 0

    val sections = timetable.entries.map { it.classGroupId to it.classGroupName }.distinct().sortedWith { a, b -> Natural.compare(a.second, b.second) }
    val teachers = data.teachers.filter { t -> timetable.entries.any { it.teacherId == t.id } }.sortedBy { it.name.lowercase() }
    val chosenSection by vm.sectionId.collectAsStateWithLifecycle()
    val sectionId = chosenSection ?: sections.firstOrNull()?.first
    val chosenTeacher by vm.teacherId.collectAsStateWithLifecycle()
    val teacherId = fixedTeacherId ?: chosenTeacher ?: teachers.firstOrNull()?.id
    var picking by remember { mutableStateOf(false) }

    val dayPeriods = data.periods.filter { it.day == day }.sortedBy { it.order }
    val shown = timetable.entries.filter {
        it.day == day && if (view == "section") it.classGroupId == sectionId else it.teacherId == teacherId
    }

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            when (mode) {
                "section" -> PickerField("Section", sections.firstOrNull { it.first == sectionId }?.second ?: "Choose", { picking = true })
                "teacher" -> PickerField("Teacher", teachers.firstOrNull { it.id == teacherId }?.name ?: "Choose", { picking = true })
                else -> Text(data.teachers.firstOrNull { it.id == teacherId }?.name ?: "", style = MaterialTheme.typography.titleMedium)
            }
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                days.forEach { d -> Pill(Dates.dayShort[d], d == day) { vm.day.value = d } }
            }
        }
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(dayPeriods) { p -> PeriodRow(p, shown.filter { it.periodId == p.id }, view) }
        }
    }

    if (picking) {
        if (view == "section") {
            PickerDialog("Choose a section", sections.map { PickerOption(it.first, it.second) }, sectionId,
                onPick = { vm.sectionId.value = it; picking = false }, onDismiss = { picking = false })
        } else {
            PickerDialog("Choose a teacher", teachers.map { PickerOption(it.id, it.name) }, teacherId,
                onPick = { vm.teacherId.value = it; picking = false }, onDismiss = { picking = false })
        }
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
