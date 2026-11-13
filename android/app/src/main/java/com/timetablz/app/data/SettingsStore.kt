package com.timetablz.app.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.datastore.preferences.core.MutablePreferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

private val Context.dataStore by preferencesDataStore(name = "settings")

/** What the app remembers. me: school id -> the teacher chosen as "I am". */
data class Settings(
    val theme: String = "system",
    val schoolId: Int? = null,
    val notifyCover: Boolean = false,
    val userEmail: String? = null,
    val me: Map<Int, Int> = emptyMap(),
    val notified: Set<String> = emptySet(),
    /** The opening animation has been seen in full once. */
    val introSeen: Boolean = false,
    /** False only for the placeholder before the saved settings have been read. */
    val loaded: Boolean = false,
)

/** Settings in DataStore; the sign-in token encrypted with a key kept in the phone's keystore. */
class SettingsStore(private val context: Context) {
    private object K {
        val theme = stringPreferencesKey("theme")
        val school = intPreferencesKey("school_id")
        val notify = booleanPreferencesKey("notify_cover")
        val email = stringPreferencesKey("user_email")
        val token = stringPreferencesKey("token_enc")
        val notified = stringSetPreferencesKey("notified")
        val intro = booleanPreferencesKey("intro_seen")
        fun me(schoolId: Int) = intPreferencesKey("me_$schoolId")
    }

    val settings: Flow<Settings> = context.dataStore.data.map { p ->
        Settings(
            theme = p[K.theme] ?: "system",
            schoolId = p[K.school]?.takeIf { it > 0 },
            notifyCover = p[K.notify] ?: false,
            userEmail = p[K.email],
            me = p.asMap().mapNotNull { (k, v) ->
                val id = k.name.removePrefix("me_").takeIf { k.name.startsWith("me_") }?.toIntOrNull()
                if (id != null && v is Int && v > 0) id to v else null
            }.toMap(),
            notified = p[K.notified] ?: emptySet(),
            introSeen = p[K.intro] ?: false,
            loaded = true,
        )
    }

    suspend fun current(): Settings = settings.first()

    private suspend fun set(block: (MutablePreferences) -> Unit) {
        context.dataStore.edit { block(it) }
    }

    suspend fun setTheme(v: String) = set { it[K.theme] = v }

    suspend fun setSchool(id: Int?) = set { p ->
        if (id == null) p.remove(K.school) else p[K.school] = id
        Unit
    }

    suspend fun setNotify(on: Boolean) = set { it[K.notify] = on }

    suspend fun setIntroSeen() = set { it[K.intro] = true }

    suspend fun setEmail(email: String?) = set { p ->
        if (email == null) p.remove(K.email) else p[K.email] = email
        Unit
    }

    suspend fun setMe(schoolId: Int, teacherId: Int?) = set { p ->
        if (teacherId == null) p.remove(K.me(schoolId)) else p[K.me(schoolId)] = teacherId
        Unit
    }

    suspend fun addNotified(keys: Collection<String>) = set { p ->
        p[K.notified] = ((p[K.notified] ?: emptySet()) + keys).toList().takeLast(300).toSet()
    }

    suspend fun token(): String? = context.dataStore.data.first()[K.token]?.let { TokenCipher.decrypt(it) }

    suspend fun setToken(token: String?) = set { p ->
        if (token == null) p.remove(K.token) else p[K.token] = TokenCipher.encrypt(token)
        Unit
    }

    /** Signing out: forget the account, keep the theme. */
    suspend fun clearAccount() = set { p ->
        val theme = p[K.theme]
        val intro = p[K.intro]
        p.clear()
        if (theme != null) p[K.theme] = theme
        if (intro != null) p[K.intro] = intro
        Unit
    }
}

/** AES-GCM with a key that never leaves the Android keystore. */
private object TokenCipher {
    private const val ALIAS = "timetablz_token"

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return gen.generateKey()
    }

    fun encrypt(plain: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, key())
        val out = c.doFinal(plain.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(c.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(out, Base64.NO_WRAP)
    }

    fun decrypt(stored: String): String? = runCatching {
        val (iv, data) = stored.split(":", limit = 2)
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
        String(c.doFinal(Base64.decode(data, Base64.NO_WRAP)), Charsets.UTF_8)
    }.getOrNull()
}
