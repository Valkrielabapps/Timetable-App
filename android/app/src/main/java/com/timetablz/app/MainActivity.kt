package com.timetablz.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.timetablz.app.ui.TimetablzApp
import com.timetablz.app.ui.theme.TimetablzTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TimetablzTheme { TimetablzApp() }
        }
    }
}
