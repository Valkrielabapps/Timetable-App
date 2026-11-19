package com.timetablz.app.ui

import android.content.res.Configuration
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.timetablz.app.data.Dates
import com.timetablz.app.data.WeekCell
import com.timetablz.app.data.WeekLayout

private val LabelWidth = 30.dp

/**
 * A whole week in one frame: days across, periods down, sized to the screen's
 * width so it never scrolls sideways. Turned sideways, the cells get the room
 * to show more of each name.
 */
@Composable
fun WeekGrid(layout: WeekLayout, cells: Map<Int, WeekCell>, today: Int?, modifier: Modifier = Modifier) {
    val c = MaterialTheme.colorScheme
    val landscape = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE
    val rowHeight = if (landscape) 44.dp else 54.dp
    val small = MaterialTheme.typography.labelSmall

    BoxWithConstraints(modifier.fillMaxWidth().clip(Rounded).border(1.dp, c.outlineVariant, Rounded)) {
        val cellWidth = (maxWidth - LabelWidth) / layout.days.size.coerceAtLeast(1)
        Column {
            Row(Modifier.background(c.surfaceVariant)) {
                Box(Modifier.width(LabelWidth))
                layout.days.forEach { d ->
                    Text(
                        Dates.dayShort[d],
                        Modifier.width(cellWidth).padding(vertical = 6.dp),
                        style = small,
                        textAlign = TextAlign.Center,
                        fontWeight = if (d == today) FontWeight.Bold else FontWeight.Normal,
                        color = if (d == today) c.onSurface else c.onSurfaceVariant,
                    )
                }
            }
            layout.rows.forEach { row ->
                if (row.band) {
                    Text(
                        row.label,
                        Modifier.fillMaxWidth().background(c.surfaceVariant).padding(vertical = 2.dp),
                        style = small.copy(fontSize = 10.sp),
                        textAlign = TextAlign.Center,
                        color = c.onSurfaceVariant,
                        maxLines = 1,
                    )
                    return@forEach
                }
                // A row is as tall as its fullest cell: a block names every teacher.
                Row(Modifier.height(IntrinsicSize.Min).heightIn(min = rowHeight).border(0.5.dp, c.outlineVariant)) {
                    Box(Modifier.width(LabelWidth).fillMaxHeight(), contentAlignment = Alignment.Center) {
                        Text(row.label, style = small, color = c.onSurfaceVariant, maxLines = 1)
                    }
                    layout.days.forEach { d ->
                        val period = layout.at(d, row.order)
                        val cell = period?.let { cells[it.id] }
                        Box(
                            Modifier.width(cellWidth).fillMaxHeight().border(0.5.dp, c.outlineVariant)
                                .then(
                                    when {
                                        period == null -> Modifier.background(c.surfaceVariant)
                                        cell != null -> Modifier.padding(2.dp).clip(RoundedSmall).background(c.surfaceContainerHigh)
                                        else -> Modifier
                                    },
                                )
                                .padding(horizontal = 3.dp, vertical = 2.dp),
                        ) {
                            if (cell != null) CellText(cell, landscape)
                            else if (period != null && !period.isLesson) {
                                Text(period.label ?: "", style = small.copy(fontSize = 9.sp), color = c.onSurfaceVariant, maxLines = 2)
                            }
                        }
                    }
                }
            }
        }
    }
}

private val RoundedSmall = androidx.compose.foundation.shape.RoundedCornerShape(4.dp)

@Composable
private fun CellText(cell: WeekCell, landscape: Boolean) {
    val c = MaterialTheme.colorScheme
    Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
        Text(
            cell.top,
            style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp, lineHeight = 12.sp),
            fontWeight = FontWeight.SemiBold,
            color = c.onSurface,
            maxLines = if (landscape) 1 else 2,
            overflow = TextOverflow.Ellipsis,
        )
        cell.lines.forEach { line ->
            Text(
                line,
                style = MaterialTheme.typography.labelSmall.copy(fontSize = 9.sp, lineHeight = 11.sp),
                color = c.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}
