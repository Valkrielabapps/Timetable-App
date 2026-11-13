package com.timetablz.app.ui

import android.provider.Settings as AndroidSettings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

/** How long the name stays up from the moment it appears, fade-in included. */
const val INTRO_MILLIS = 4000L

/**
 * The opening: after the launch screen's mark fades away, the Timetablz name
 * and line fade in on the same black, rise gently into place, and hold for
 * about four seconds before the app fades in. One continuous movement -
 * nothing overlaps or swaps half-way. Tap to skip; skipped when the phone has
 * animations turned off.
 */
@Composable
fun IntroScreen(onFinished: () -> Unit) {
    val context = LocalContext.current
    val animationsOff = remember {
        AndroidSettings.Global.getFloat(context.contentResolver, AndroidSettings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
    }
    val shown = remember { Animatable(if (animationsOff) 1f else 0f) }
    LaunchedEffect(Unit) {
        if (!animationsOff) shown.animateTo(1f, tween(700, easing = FastOutSlowInEasing))
        delay(if (animationsOff) 600L else INTRO_MILLIS - 700L)
        onFinished()
    }
    val t = shown.value

    Box(
        Modifier
            .fillMaxSize()
            .background(Color(0xFF0A0A0A))
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { onFinished() },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.graphicsLayer {
                alpha = t
                translationY = 24f * (1f - t)
            },
        ) {
            Text("Timetablz", color = Color.White, fontSize = 40.sp, fontWeight = FontWeight.Bold)
            Text(
                "Clash-free timetables, made in minutes",
                color = Color.White.copy(alpha = 0.6f),
                fontSize = 14.sp,
                modifier = Modifier.padding(horizontal = 24.dp),
            )
        }
    }
}
