package com.timetablz.app.ui

import android.provider.Settings as AndroidSettings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val Night = Color(0xFF0A0A0A)

/** 0 before [start], 1 after [end], eased in between. */
private fun seg(t: Float, start: Float, end: Float): Float =
    FastOutSlowInEasing.transform(((t - start) / (end - start)).coerceIn(0f, 1f))

/**
 * The opening: a week's grid draws itself cell by cell, lessons drop into
 * place the way the solver fills a timetable, and the grid settles into the
 * Timetablz wordmark. It grows out of the launch screen's mark (same black,
 * same cells), so the two read as one moment.
 *
 * [full]: the whole thing (about 2.4 s), on the very first open. Otherwise a
 * short version while the app gets ready. Tap to skip. Skipped entirely when
 * the phone has animations turned off.
 */
@Composable
fun IntroScreen(full: Boolean, onFinished: () -> Unit) {
    val context = LocalContext.current
    val animationsOff = remember {
        AndroidSettings.Global.getFloat(context.contentResolver, AndroidSettings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
    }
    val progress = remember { Animatable(if (full) 0f else 0.62f) }
    LaunchedEffect(full) {
        if (!animationsOff) {
            progress.animateTo(1f, tween(durationMillis = if (full) 2400 else 650, easing = LinearEasing))
        } else {
            progress.snapTo(1f)
        }
        onFinished()
    }
    val t = progress.value

    Box(
        Modifier
            .fillMaxSize()
            .background(Night)
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { onFinished() },
        contentAlignment = Alignment.Center,
    ) {
        // The grid: 6 days across, 7 periods down.
        val gridOut = seg(t, 0.62f, 0.82f)  // lifts and fades as the name arrives
        Canvas(
            Modifier
                .size(width = 216.dp, height = 252.dp)
                .graphicsLayer {
                    alpha = 1f - gridOut
                    val s = 1f - 0.25f * gridOut
                    scaleX = s
                    scaleY = s
                    translationY = -60f * gridOut
                }
        ) {
            val cols = 6
            val rows = 7
            val gap = size.width * 0.045f
            val cell = (size.width - gap * (cols - 1)) / cols
            val radius = CornerRadius(cell * 0.18f)
            for (r in 0 until rows) for (c in 0 until cols) {
                val x = c * (cell + gap)
                val y = r * (cell + gap)
                // Each cell appears in a wave from the top left...
                val delay = (c + r) * 0.022f
                val appear = seg(t, 0.02f + delay, 0.22f + delay)
                if (appear <= 0f) continue
                val inset = cell * 0.5f * (1f - appear)
                drawRoundRect(
                    color = Color.White.copy(alpha = 0.55f * appear),
                    topLeft = Offset(x + inset, y + inset),
                    size = Size(cell - 2 * inset, cell - 2 * inset),
                    cornerRadius = radius,
                    style = Stroke(width = 1.6.dp.toPx()),
                )
                // ...then the lessons drop in, a third of the week, in their own order.
                if ((r * 5 + c * 3) % 3 == 0) {
                    val order = ((r * 7 + c * 11) % 17) / 17f
                    val fill = seg(t, 0.28f + order * 0.26f, 0.38f + order * 0.26f)
                    if (fill > 0f) {
                        val shrink = cell * 0.22f * (1f - fill)
                        drawRoundRect(
                            color = Color.White.copy(alpha = fill),
                            topLeft = Offset(x + shrink, y + shrink - 6f * (1f - fill)),
                            size = Size(cell - 2 * shrink, cell - 2 * shrink),
                            cornerRadius = radius,
                        )
                    }
                }
            }
        }

        // The name, tightening into place.
        val name = seg(t, 0.66f, 0.92f)
        val line = seg(t, 0.78f, 1f)
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.offset(y = (16 * (1f - name)).dp).graphicsLayer { alpha = name },
        ) {
            Text(
                "Timetablz",
                color = Color.White,
                fontSize = 40.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = (10f * (1f - name)).sp,
            )
            Text(
                "Clash-free timetables, made in minutes",
                color = Color.White.copy(alpha = 0.6f * line),
                fontSize = 14.sp,
                modifier = Modifier.padding(horizontal = 24.dp),
            )
        }
    }
}
