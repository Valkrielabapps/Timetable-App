package com.timetablz.app

import android.app.Application
import com.timetablz.app.data.AppContainer

class TimetablzApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
