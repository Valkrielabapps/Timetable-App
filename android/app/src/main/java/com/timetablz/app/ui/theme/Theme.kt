package com.timetablz.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// The website's black-and-white look, and its night-time inverse. No
// wallpaper colours (dynamic colour), so every phone shows the same app.
private val Light = lightColorScheme(
    primary = Ink, onPrimary = Color.White,
    primaryContainer = Slate100, onPrimaryContainer = Ink,
    secondary = Slate700, onSecondary = Color.White,
    secondaryContainer = Slate100, onSecondaryContainer = Ink,
    tertiary = Emerald700,
    background = Color.White, onBackground = Ink,
    surface = Color.White, onSurface = Ink,
    surfaceVariant = Slate50, onSurfaceVariant = Slate500,
    surfaceContainer = Slate50, surfaceContainerLow = Color.White, surfaceContainerHigh = Slate100,
    outline = Slate300, outlineVariant = Slate200,
    error = Red600,
)

private val Dark = darkColorScheme(
    primary = Color.White, onPrimary = Ink,
    primaryContainer = Color(0xFF262626), onPrimaryContainer = Color.White,
    secondary = Color(0xFFCBD5E1), onSecondary = Ink,
    secondaryContainer = Color(0xFF262626), onSecondaryContainer = Color.White,
    tertiary = Color(0xFF34D399),
    background = Color(0xFF0A0A0A), onBackground = Color.White,
    surface = Color(0xFF0A0A0A), onSurface = Color.White,
    surfaceVariant = Color(0xFF171717), onSurfaceVariant = Color(0xFF94A3B8),
    surfaceContainer = Color(0xFF171717), surfaceContainerLow = Color(0xFF0A0A0A), surfaceContainerHigh = Color(0xFF262626),
    outline = Color(0xFF525252), outlineVariant = Color(0xFF2E2E2E),
    error = Color(0xFFF87171),
)

/** theme: "system", "light" or "dark" - chosen in Settings. */
@Composable
fun TimetablzTheme(theme: String = "system", content: @Composable () -> Unit) {
    val dark = when (theme) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }
    MaterialTheme(colorScheme = if (dark) Dark else Light, typography = Typography, content = content)
}
