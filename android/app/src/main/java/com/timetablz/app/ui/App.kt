package com.timetablz.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.timetablz.app.ui.theme.TimetablzTheme

/** The whole app: sign in → terms → school → Menu / Substitution / Settings. */
@Composable
fun TimetablzApp(openTab: String? = null) {
    val session: SessionViewModel = viewModel(factory = AppViewModels.Factory)
    val ui by session.ui.collectAsStateWithLifecycle()
    val settings by session.settings.collectAsStateWithLifecycle()

    TimetablzTheme(settings.theme) {
        Surface(color = MaterialTheme.colorScheme.background) {
            val user = ui.user
            when {
                ui.starting -> Loading("Opening Timetablz…")
                user == null -> LoginScreen(session, ui)
                user.needsTerms -> TermsScreen(session, ui)
                ui.school == null -> SchoolPicker(session, ui)
                else -> Home(session, openTab)
            }
        }
    }
}

/** Every page and its title. The first three are the bottom bar's. */
object Routes {
    const val MENU = "menu"
    const val SUBSTITUTION = "substitution"
    const val SETTINGS = "settings"
    const val MAKE_COVER = "menu/make-substitutions"
    const val MY_TIMETABLE = "menu/my-timetable"
    const val TEACHERS = "menu/teachers"
    const val CLASSES = "menu/classes"

    val titles = mapOf(
        MAKE_COVER to "Make substitutions",
        MY_TIMETABLE to "My timetable",
        TEACHERS to "Teachers' timetables",
        CLASSES to "Class timetables",
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Home(session: SessionViewModel, openTab: String?) {
    val nav = rememberNavController()
    val ui by session.ui.collectAsStateWithLifecycle()
    val data by session.schoolData.collectAsStateWithLifecycle()
    val settings by session.settings.collectAsStateWithLifecycle()
    val school = ui.school ?: return
    val c = MaterialTheme.colorScheme
    val route = nav.currentBackStackEntryAsState().value?.destination?.route
    val subPage = Routes.titles[route]

    Scaffold(
        containerColor = c.background,
        topBar = {
            Column {
                TopAppBar(
                    navigationIcon = {
                        if (subPage != null) {
                            IconButton(onClick = { nav.popBackStack() }) {
                                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                            }
                        }
                    },
                    title = { Text(subPage ?: school.name, style = MaterialTheme.typography.titleMedium, maxLines = 1) },
                    actions = {
                        IconButton(onClick = { session.refresh() }) { Icon(Icons.Default.Refresh, contentDescription = "Refresh") }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = c.background),
                )
                if (ui.refreshing) LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.onSurface)
                if (ui.offline) {
                    Text(
                        "Offline: showing the last saved copy",
                        style = MaterialTheme.typography.labelMedium, color = c.onSurfaceVariant,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    )
                }
            }
        },
        bottomBar = {
            NavigationBar(containerColor = c.background) {
                val colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = c.onSurface, selectedTextColor = c.onSurface, indicatorColor = c.surfaceContainerHigh,
                    unselectedIconColor = c.onSurfaceVariant, unselectedTextColor = c.onSurfaceVariant,
                )
                val tab = when {
                    route == null || route.startsWith(Routes.MENU) -> Routes.MENU
                    else -> route
                }
                NavigationBarItem(
                    selected = tab == Routes.MENU, onClick = { nav.goTab(Routes.MENU) },
                    icon = { Icon(Icons.Default.Menu, contentDescription = null) }, label = { Text("Menu") }, colors = colors,
                )
                NavigationBarItem(
                    selected = tab == Routes.SUBSTITUTION, onClick = { nav.goTab(Routes.SUBSTITUTION) },
                    icon = { Icon(Icons.Default.Notifications, contentDescription = null) }, label = { Text("Substitution") }, colors = colors,
                )
                NavigationBarItem(
                    selected = tab == Routes.SETTINGS, onClick = { nav.goTab(Routes.SETTINGS) },
                    icon = { Icon(Icons.Default.Settings, contentDescription = null) }, label = { Text("Settings") }, colors = colors,
                )
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding)) {
            NavHost(nav, startDestination = if (openTab == "substitution") Routes.SUBSTITUTION else Routes.MENU) {
                composable(Routes.MENU) {
                    MenuScreen(school, ui.user, session.me(data, settings, ui)) { nav.navigate(it) }
                }
                composable(Routes.SETTINGS) { SettingsScreen(session) }
                composable(Routes.SUBSTITUTION) {
                    WithData(session, data) { d -> MySubstitutionsScreen(session, d) { nav.goTab(Routes.SETTINGS) } }
                }
                composable(Routes.MAKE_COVER) { WithData(session, data) { d -> CoverScreen(session, d) } }
                composable(Routes.MY_TIMETABLE) {
                    WithData(session, data) { d ->
                        val me = session.me(d, settings, ui)
                        if (me == null) {
                            Message("Which teacher are you?", "Choose yourself in Settings → I am, and your timetable shows here.",
                                "Open Settings") { nav.goTab(Routes.SETTINGS) }
                        } else {
                            TimetableScreen(d, mode = "mine", fixedTeacherId = me.id)
                        }
                    }
                }
                composable(Routes.TEACHERS) { WithData(session, data) { d -> TimetableScreen(d, mode = "teacher") } }
                composable(Routes.CLASSES) { WithData(session, data) { d -> TimetableScreen(d, mode = "section") } }
            }
        }
    }
}

/** The school's data, or a loading / couldn't-load message in its place. */
@Composable
private fun WithData(session: SessionViewModel, data: com.timetablz.app.data.SchoolData?, content: @Composable (com.timetablz.app.data.SchoolData) -> Unit) {
    val ui by session.ui.collectAsStateWithLifecycle()
    when {
        data != null -> content(data)
        ui.refreshing || ui.loading -> Loading()
        else -> Message("Couldn't load the school", ui.error ?: "Check your connection and try again.", "Try again") { session.refresh() }
    }
}

/** Bottom-bar navigation: one copy of each tab, each keeping its place. */
private fun NavHostController.goTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
