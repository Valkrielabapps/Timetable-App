# Timetablz for Android

The phone app for timetablz.com: sign in (email or Google), accept the Terms,
see timetables by section or teacher, and arrange the day's cover. It uses the
same backend and accounts as the website (`https://timetablz.com/api`).

Open this folder in Android Studio, sync Gradle, and Run.

## Google sign-in setup (once)

Google only signs in apps it knows. In Google Cloud Console, in the same project
as the website's OAuth client (`279654108028-...`):

1. **APIs & Services → Credentials → Create credentials → OAuth client ID → Android.**
2. Package name: `com.timetablz.app`.
3. SHA-1 certificate fingerprint of the key that signs the app:
   - while developing, the debug key. In Android Studio's Gradle panel run
     `app → Tasks → android → signingReport`, or in a terminal:
     `keytool -list -v -keystore "%USERPROFILE%\.android\debug.keystore" -alias androiddebugkey -storepass android -keypass android`
   - for the Play Store, add another Android client with the **App signing key**
     SHA-1 from Play Console → Setup → App signing.
4. Save. Nothing goes in the app itself: it sends the website's web client ID
   (`timetablz.googleWebClientId` in `gradle.properties`), and the backend
   checks tokens against that, exactly as for the website.

If the Android client is missing or its SHA-1 is wrong, the account chooser
fails with a "developer error"-type message.
