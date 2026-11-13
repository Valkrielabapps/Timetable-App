package com.timetablz.app.data

import android.content.Context
import androidx.room.Room
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

/**
 * The app's single set of shared objects, made once (TimetablzApplication).
 * ViewModels and the background worker take what they need from here.
 * Hand-wired rather than Hilt: a handful of objects doesn't need a framework.
 */
class AppContainer(context: Context) {
    val tokens = TokenHolder()
    val store = SettingsStore(context)

    private val unauthorized = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    /** Fires when the server says the sign-in is no longer valid. */
    val signedOut: SharedFlow<Unit> = unauthorized

    private val api = Network.api(tokens) { unauthorized.tryEmit(Unit) }

    private val db = Room.databaseBuilder(context, CacheDb::class.java, "timetablz.db")
        .fallbackToDestructiveMigration()
        .build()

    val auth = AuthRepository(api, tokens, store, db.cache(), Network.json)
    val schools = SchoolRepository(api, db.cache(), Network.json)
    val cover = CoverRepository(api, db.cache(), Network.json)
}
