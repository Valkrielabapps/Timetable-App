package com.timetablz.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.timetablz.app.data.Session
import com.timetablz.app.ui.theme.Ink
import com.timetablz.app.ui.theme.Slate100
import com.timetablz.app.ui.theme.Slate500
import kotlinx.coroutines.launch

/** The whole app: sign in → (terms) → school → Timetable / Cover. */
@Composable
fun TimetablzApp() {
    val context = LocalContext.current
    val state = remember { AppState(Session(context.applicationContext)) }
    LaunchedEffect(Unit) { state.resume() }

    val user = state.user
    when {
        state.starting -> Loading("Opening Timetablz…")
        user == null -> LoginScreen(state)
        user.needsTerms -> TermsScreen(state)
        state.school == null -> SchoolPicker(state)
        else -> Home(state)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Home(state: AppState) {
    val scope = rememberCoroutineScope()
    var tab by rememberSaveable { mutableStateOf("timetable") }
    var menu by remember { mutableStateOf(false) }
    val school = state.school ?: return

    Scaffold(
        containerColor = Color.White,
        topBar = {
            TopAppBar(
                title = {
                    Text(school.name, style = MaterialTheme.typography.titleMedium, maxLines = 1)
                },
                actions = {
                    IconButton(onClick = { scope.launch { state.reload() } }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                    Box {
                        IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, contentDescription = "More") }
                        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                            Text(state.user?.email ?: "", style = MaterialTheme.typography.bodySmall, color = Slate500,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
                            HorizontalDivider()
                            if (state.schools.size > 1) {
                                DropdownMenuItem(text = { Text("Switch school") }, onClick = { menu = false; state.switchSchool() })
                            }
                            DropdownMenuItem(text = { Text("Sign out") }, onClick = { menu = false; state.signOut() })
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = Color.White) {
                val colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = Ink, selectedTextColor = Ink, indicatorColor = Slate100,
                    unselectedIconColor = Slate500, unselectedTextColor = Slate500,
                )
                NavigationBarItem(
                    selected = tab == "timetable", onClick = { tab = "timetable" },
                    icon = { Icon(Icons.Default.DateRange, contentDescription = null) },
                    label = { Text("Timetable") }, colors = colors,
                )
                NavigationBarItem(
                    selected = tab == "cover", onClick = { tab = "cover" },
                    icon = { Icon(Icons.Default.Person, contentDescription = null) },
                    label = { Text("Cover") }, colors = colors,
                )
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding)) {
            val data = state.data
            if (data == null) {
                if (state.loading) Loading()
                else Message("Couldn't load the school", state.error ?: "Try again.", "Try again") {
                    scope.launch { state.reload() }
                }
            } else if (tab == "timetable") {
                TimetableScreen(state, data)
            } else {
                CoverScreen(state, data)
            }
        }
    }
}
