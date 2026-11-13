package com.timetablz.app.data

import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.timetablz.app.BuildConfig

/** The person closed Google's account chooser: not an error, nothing to show. */
class GoogleSignInCancelled : Exception()

/**
 * "Continue with Google": Google's account chooser (Credential Manager), then
 * the ID token it returns. The backend checks that token exactly as it does
 * the website's (POST /api/auth/google), so it's the same account either way.
 *
 * [context] must be an Activity - the chooser is shown over it.
 */
object GoogleSignIn {
    val configured get() = BuildConfig.GOOGLE_WEB_CLIENT_ID.isNotBlank()

    suspend fun idToken(context: Context): String {
        val option = GetSignInWithGoogleOption.Builder(BuildConfig.GOOGLE_WEB_CLIENT_ID).build()
        val request = GetCredentialRequest.Builder().addCredentialOption(option).build()
        val result = try {
            CredentialManager.create(context).getCredential(context, request)
        } catch (e: GetCredentialCancellationException) {
            throw GoogleSignInCancelled()
        } catch (e: NoCredentialException) {
            throw ApiException(0, "No Google account on this phone. Add one in Settings → Accounts, or sign in with email.")
        } catch (e: GetCredentialException) {
            throw ApiException(0, "Google sign-in didn't work (${e.type}). Try again, or sign in with email.")
        }
        val credential = result.credential
        if (credential is CustomCredential && credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
            return GoogleIdTokenCredential.createFrom(credential.data).idToken
        }
        throw ApiException(0, "Google sign-in returned something unexpected. Try again, or sign in with email.")
    }
}
