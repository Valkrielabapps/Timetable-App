package com.timetablz.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import com.timetablz.app.data.Session
import com.timetablz.app.ui.theme.TimetablzTheme
import kotlinx.coroutines.launch

/** The whole app: sign in → terms → school → Menu / Substitution / Settings. */
@Composable
fun TimetablzApp(openTab: String? = null) {
    val context = LocalContext.current
    val state = remember { AppState(Session(context.applicationContext)) }
    LaunchedEffect(Unit) { state.resume() }

    TimetablzTheme(state.theme) {
        Surface(color = MaterialTheme.colorScheme.background) {
            val user = state.user
            when {
                state.starting -> Loading("Opening Timetablz…")
                user == null -> LoginScreen(state)
                user.needsTerms -> TermsScreen(state)
                state.school == null -> SchoolPicker(state)
                else -> Home(state, openTab)
            }
        }
    }
}

/** Pages reached from the Menu, each with a back arrow. */
enum class Page(val title: String) {
    MakeCover("Make substitutions"),
    MyTimetable("My timetable"),
    TeacherTimetables("Teachers' timetables"),
    ClassTimetables("Class timetables"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Home(state: AppState, openTab: String?) {
    val scope = state.scope
    var tab by rememberSaveable { mutableStateOf(if (openTab == "substitution") "substitution" else "menu") }
    var page by rememberSaveable { mutableStateOf<Page?>(null) }
    val school = state.school ?: return
    val c = MaterialTheme.colorScheme

    BackHandler(enabled = page != null) { page = null }

    Scaffold(
        containerColor = c.background,
        topBar = {
            TopAppBar(
                navigationIcon = {
                    if (tab == "menu" && page != null) {
                        IconButton(onClick = { page = null }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
                    }
                },
                title = {
                    Text(
                        if (tab == "menu" && page != null) page!!.title else school.name,
                        style = MaterialTheme.typography.titleMedium, maxLines = 1,
                    )
                },
                actions = {
                    IconButton(onClick = { scope.launch { state.reload() } }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.background),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = c.background) {
                val colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = c.onSurface, selectedTextColor = c.onSurface, indicatorColor = c.surfaceContainerHigh,
                    unselectedIconColor = c.onSurfaceVariant, unselectedTextColor = c.onSurfaceVariant,
                )
                NavigationBarItem(
                    selected = tab == "menu", onClick = { if (tab == "menu") page = null; tab = "menu" },
                    icon = { Icon(Icons.Default.Menu, contentDescription = null) }, label = { Text("Menu") }, colors = colors,
                )
                NavigationBarItem(
                    selected = tab == "substitution", onClick = { tab = "substitution" },
                    icon = { Icon(Icons.Default.Notifications, contentDescription = null) }, label = { Text("Substitution") }, colors = colors,
                )
                NavigationBarItem(
                    selected = tab == "settings", onClick = { tab = "settings" },
                    icon = { Icon(Icons.Default.Settings, contentDescription = null) }, label = { Text("Settings") }, colors = colors,
                )
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding)) {
            val data = state.data
            if (tab == "settings") {
                SettingsScreen(state)
            } else if (data == null) {
                if (state.loading) Loading()
                else Message("Couldn't load the school", state.error ?: "Try again.", "Try again") {
                    scope.launch { state.reload() }
                }
            } else if (tab == "substitution") {
                MySubstitutionsScreen(state, data, onOpenSettings = { tab = "settings" })
            } else when (page) {
                null -> MenuScreen(state, onOpen = { page = it })
                Page.MakeCover -> CoverScreen(state, data)
                Page.MyTimetable -> {
                    val me = state.me()
                    if (me == null) Message("Which teacher are you?", "Choose yourself in Settings → I am, and your timetable shows here.", "Open Settings") { tab = "settings" }
                    else TimetableScreen(state, data, mode = "mine", fixedTeacherId = me.id)
                }
                Page.TeacherTimetables -> TimetableScreen(state, data, mode = "teacher")
                Page.ClassTimetables -> TimetableScreen(state, data, mode = "section")
            }
        }
    }
}
