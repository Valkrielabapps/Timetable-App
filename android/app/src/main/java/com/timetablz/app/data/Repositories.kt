package com.timetablz.app.data

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/** Reads and writes one kind of thing in the offline copy. */
private class Cached<T>(private val dao: CacheDao, private val json: Json, private val serializer: KSerializer<T>) {
    fun observe(id: String): Flow<T?> = dao.observe(id).map { e -> e?.let { decode(it.json) } }
    suspend fun get(id: String): T? = dao.get(id)?.let { decode(it.json) }
    suspend fun put(id: String, value: T) = dao.put(CacheEntry(id, json.encodeToString(serializer, value), System.currentTimeMillis()))
    private fun decode(s: String): T? = runCatching { json.decodeFromString(serializer, s) }.getOrNull()
}

@Serializable
data class Account(val user: User, val schools: List<School>)

/** Signing in and out, the terms, and which schools this account has. */
class AuthRepository(
    private val api: TimetablzApi,
    private val tokens: TokenHolder,
    private val store: SettingsStore,
    private val dao: CacheDao,
    json: Json,
) {
    private val account = Cached(dao, json, Account.serializer())

    /** A saved sign-in from last time, if any. */
    suspend fun restore(): Boolean {
        if (tokens.token == null) tokens.token = store.token()
        return tokens.token != null
    }

    suspend fun login(email: String, password: String): User = save(apiCall { api.login(LoginRequest(email.trim(), password)) })
    suspend fun google(idToken: String): User = save(apiCall { api.google(GoogleRequest(idToken)) })

    private suspend fun save(r: TokenResponse): User {
        tokens.token = r.accessToken
        store.setToken(r.accessToken)
        store.setEmail(r.user.email)
        return r.user
    }

    suspend fun me(): User = apiCall { api.me() }.also { store.setEmail(it.email) }
    suspend fun acceptTerms(version: String): User = apiCall { api.acceptTerms(TermsRequest(version)) }

    suspend fun schools(user: User): List<School> =
        apiCall { api.schools() }.also { account.put("account", Account(user, it)) }

    /** Who was signed in and their schools, as last seen - for opening with no signal. */
    suspend fun cachedAccount(): Account? = account.get("account")

    suspend fun signOut() {
        tokens.token = null
        store.clearAccount()
        dao.clear()
    }
}

/** One school's periods, teachers and current timetable. */
class SchoolRepository(private val api: TimetablzApi, dao: CacheDao, json: Json) {
    private val cache = Cached(dao, json, SchoolData.serializer())

    fun data(schoolId: Int): Flow<SchoolData?> = cache.observe("school:$schoolId")

    suspend fun refresh(schoolId: Int): SchoolData {
        val periods = apiCall { api.periods(schoolId) }
        val teachers = apiCall { api.teachers(schoolId) }
        val versions = apiCall { api.timetables(schoolId) }
        // The version the school works from - the one the website's Timetable tab shows.
        val pick = versions.firstOrNull { it.isCurrent } ?: versions.filter { it.status == "draft" }.maxByOrNull { it.id }
        val sections = apiCall { api.classGroups(schoolId) }.associateBy { it.id }
        // The timetable names a section only "A"; every screen should say "Grade 6 A".
        val timetable = pick?.let { apiCall { api.timetable(it.id) } }?.let { tt ->
            tt.copy(entries = tt.entries.map { e -> sections[e.classGroupId]?.let { e.copy(classGroupName = it.label) } ?: e })
        }
        return SchoolData(periods, teachers, timetable).also { cache.put("school:$schoolId", it) }
    }
}

/** The school's saved cover, saving a day's, its summary and emailing it. */
class CoverRepository(private val api: TimetablzApi, dao: CacheDao, json: Json) {
    private val cache = Cached(dao, json, ListSerializer(SavedCover.serializer()))

    fun covers(schoolId: Int): Flow<List<SavedCover>?> = cache.observe("covers:$schoolId")

    suspend fun refresh(schoolId: Int): List<SavedCover> =
        apiCall { api.covers(schoolId) }.map { it.toDomain() }.also { cache.put("covers:$schoolId", it) }

    suspend fun save(schoolId: Int, body: SaveCoverRequest) {
        apiCall { api.saveCover(schoolId, body) }
        refresh(schoolId)
    }

    suspend fun summary(schoolId: Int, date: String): Summary = apiCall { api.summary(schoolId, date) }.toDomain()

    suspend fun notify(schoolId: Int, date: String): NotifyResult = apiCall { api.notify(schoolId, NotifyRequest(date)) }.toDomain()
}
