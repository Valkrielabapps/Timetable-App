package com.timetablz.app.data

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

/**
 * The offline copy: each thing the app shows ("school:12" - periods, teachers
 * and the timetable; "covers:12"; "account") stored as the JSON it was last
 * fetched as. Screens read from here, so they open instantly and work with no
 * signal; a refresh replaces the copy and the screens update themselves.
 */
@Entity(tableName = "cache")
data class CacheEntry(@PrimaryKey val id: String, val json: String, val updatedAt: Long)

@Dao
interface CacheDao {
    @Query("SELECT * FROM cache WHERE id = :id")
    fun observe(id: String): Flow<CacheEntry?>

    @Query("SELECT * FROM cache WHERE id = :id")
    suspend fun get(id: String): CacheEntry?

    @Upsert
    suspend fun put(entry: CacheEntry)

    @Query("DELETE FROM cache")
    suspend fun clear()
}

@Database(entities = [CacheEntry::class], version = 1, exportSchema = false)
abstract class CacheDb : RoomDatabase() {
    abstract fun cache(): CacheDao
}
