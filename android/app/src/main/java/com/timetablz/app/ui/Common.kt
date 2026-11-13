package com.timetablz.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.timetablz.app.ui.theme.Ink
import com.timetablz.app.ui.theme.Slate200
import com.timetablz.app.ui.theme.Slate500

val Rounded = RoundedCornerShape(10.dp)

/** The website's black button. */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, busy: Boolean = false) {
    Button(
        onClick = onClick,
        enabled = enabled && !busy,
        modifier = modifier.heightIn(min = 48.dp),
        shape = RoundedCornerShape(8.dp),
        colors = ButtonDefaults.buttonColors(containerColor = Ink, contentColor = Color.White),
    ) {
        if (busy) CircularProgressIndicator(strokeWidth = 2.dp, color = Color.White, modifier = Modifier.padding(end = 8.dp).size(18.dp))
        Text(text)
    }
}

/** The website's outlined grey button. */
@Composable
fun SecondaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = 44.dp),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, Slate200),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = Ink),
    ) { Text(text) }
}

/** A white card with the website's thin border. */
@Composable
fun Card(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable () -> Unit) {
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .border(1.dp, Slate200, Rounded)
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier),
        shape = Rounded,
        color = Color.White,
    ) { content() }
}

/** A small rounded pill: black when chosen, outlined otherwise. */
@Composable
fun Pill(text: String, selected: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(50)
    Box(
        modifier = Modifier
            .then(if (selected) Modifier.background(Ink, shape) else Modifier.border(1.dp, Slate200, shape))
            .clickable { onClick() }
            .padding(horizontal = 14.dp, vertical = 7.dp),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, color = if (selected) Color.White else Ink)
    }
}

@Composable
fun Loading(text: String = "Loading…") {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
            CircularProgressIndicator(color = Ink)
            Text(text, color = Slate500)
        }
    }
}

@Composable
fun Message(title: String, body: String, action: String? = null, onAction: (() -> Unit)? = null) {
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(body, color = Slate500, style = MaterialTheme.typography.bodyMedium)
            if (action != null && onAction != null) SecondaryButton(action, onAction, Modifier.padding(top = 8.dp))
        }
    }
}

/** A tappable field that opens [PickerDialog]: "Grade 6 A ▾". */
@Composable
fun PickerField(label: String, value: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = Slate500)
        Row(
            modifier = Modifier
                .padding(top = 4.dp)
                .fillMaxWidth()
                .border(1.dp, Slate200, RoundedCornerShape(8.dp))
                .clickable { onClick() }
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(value, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
            Text("▾", color = Slate500)
        }
    }
}

data class PickerOption<T>(val value: T, val label: String, val note: String? = null, val group: String? = null)

/** A searchable list in a dialog, optionally in groups ("Suggested", "Also free"). */
@Composable
fun <T> PickerDialog(
    title: String,
    options: List<PickerOption<T>>,
    selected: T?,
    onPick: (T) -> Unit,
    onDismiss: () -> Unit,
    searchable: Boolean = options.size > 12,
) {
    var query by remember { mutableStateOf("") }
    val shown = if (query.isBlank()) options else options.filter { it.label.contains(query.trim(), ignoreCase = true) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title, style = MaterialTheme.typography.titleMedium) },
        text = {
            Column {
                if (searchable) {
                    OutlinedTextField(
                        value = query, onValueChange = { query = it }, singleLine = true,
                        placeholder = { Text("Search") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                    )
                }
                // A group's heading goes above its first option.
                val rows = shown.mapIndexed { i, o -> o to (o.group != null && (i == 0 || shown[i - 1].group != o.group)) }
                LazyColumn(Modifier.heightIn(max = 420.dp)) {
                    items(rows) { (o, heading) ->
                        Column {
                            if (heading) {
                                Text(o.group ?: "", style = MaterialTheme.typography.labelMedium, color = Slate500,
                                    modifier = Modifier.padding(top = 10.dp, bottom = 4.dp))
                            }
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { onPick(o.value) }
                                    .padding(vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Text(o.label, fontWeight = if (o.value == selected) FontWeight.SemiBold else FontWeight.Normal)
                                    o.note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Slate500) }
                                }
                                if (o.value == selected) Text("✓")
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close", color = Ink) } },
        containerColor = Color.White,
    )
}
