package com.timetablz.app.ui

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.CreationExtras
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.timetablz.app.TimetablzApplication

/** Makes every ViewModel with what it needs from the AppContainer. */
object AppViewModels {
    private fun CreationExtras.container() =
        (this[ViewModelProvider.AndroidViewModelFactory.APPLICATION_KEY] as TimetablzApplication).container

    val Factory: ViewModelProvider.Factory = viewModelFactory {
        initializer { SessionViewModel(container()) }
        initializer { CoverViewModel(container()) }
        initializer { MySubstitutionsViewModel(container()) }
        initializer { TimetableViewModel() }
    }
}
