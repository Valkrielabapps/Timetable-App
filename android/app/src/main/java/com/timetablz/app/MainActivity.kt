package com.timetablz.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.timetablz.app.ui.TimetablzApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        // The mark on black while Android starts the app; the opening animation carries on from it.
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // A cover notification opens straight on the Substitution page.
        val open = intent?.getStringExtra("open")
        setContent { TimetablzApp(openTab = open) }
    }
}
