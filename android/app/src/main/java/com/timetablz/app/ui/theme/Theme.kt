package com.timetablz.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Always the website's light, black-and-white look - no wallpaper colours
// (dynamic colour) and no dark theme for now, so every phone shows the same app.
private val Colors = lightColorScheme(
    primary = Ink,
    onPrimary = Color.White,
    primaryContainer = Slate100,
    onPrimaryContainer = Ink,
    secondary = Slate700,
    onSecondary = Color.White,
    secondaryContainer = Slate100,
    onSecondaryContainer = Ink,
    tertiary = Emerald700,
    background = Color.White,
    onBackground = Ink,
    surface = Color.White,
    onSurface = Ink,
    surfaceVariant = Slate50,
    onSurfaceVariant = Slate500,
    surfaceContainer = Slate50,
    surfaceContainerLow = Color.White,
    surfaceContainerHigh = Slate100,
    outline = Slate300,
    outlineVariant = Slate200,
    error = Red600,
)

@Composable
fun TimetablzTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Colors, typography = Typography, content = content)
}
