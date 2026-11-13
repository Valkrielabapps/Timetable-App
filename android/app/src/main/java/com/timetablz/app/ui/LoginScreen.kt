package com.timetablz.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.timetablz.app.data.ApiException
import com.timetablz.app.data.GoogleSignIn
import com.timetablz.app.data.GoogleSignInCancelled
import com.timetablz.app.ui.theme.Ink
import com.timetablz.app.ui.theme.Red600
import com.timetablz.app.ui.theme.Slate500
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(session: SessionViewModel, ui: SessionUi) {
    val uri = LocalUriHandler.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var email by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val busy = ui.authBusy != null

    fun google() {
        if (busy) return
        session.showAuthError(null)
        // The chooser only lasts while this screen is up; signing in itself runs in the ViewModel.
        scope.launch {
            try {
                session.signInWithGoogle(GoogleSignIn.idToken(context))
            } catch (e: GoogleSignInCancelled) {
                // Closed the chooser: nothing to say.
            } catch (e: ApiException) {
                session.showAuthError(e.message)
            }
        }
    }

    fun submit() {
        if (email.isBlank() || password.isEmpty() || busy) return
        session.signIn(email, password)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 48.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Timetablz", fontSize = 30.sp, fontWeight = FontWeight.Bold)
        Text("Sign in with your Timetablz account", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (GoogleSignIn.configured) {
            GoogleButton(onClick = ::google, busy = ui.authBusy == "google", modifier = Modifier.fillMaxWidth().padding(top = 16.dp))
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 4.dp)) {
                HorizontalDivider(Modifier.weight(1f))
                Text("  or with email  ", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                HorizontalDivider(Modifier.weight(1f))
            }
        }
        OutlinedTextField(
            value = email, onValueChange = { email = it }, label = { Text("Email") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = password, onValueChange = { password = it }, label = { Text("Password") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { submit() }),
            modifier = Modifier.fillMaxWidth(),
        )
        ui.authError?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
        PrimaryButton("Sign in", ::submit, Modifier.fillMaxWidth(), enabled = email.isNotBlank() && password.isNotEmpty(),
            busy = ui.authBusy == "email")
        Text(
            "Forgot your password? Reset it on timetablz.com. New here? Sign in and you'll be asked to accept " +
                "the Terms first.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        SecondaryButton("Open timetablz.com", { uri.openUri("https://timetablz.com") }, Modifier.fillMaxWidth())
    }
}

@Composable
fun TermsScreen(session: SessionViewModel, ui: SessionUi) {
    val uri = LocalUriHandler.current
    var agreed by rememberSaveable { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Terms and conditions", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 24.dp))
        Text(
            "Before you use Timetablz, please read and accept our Terms of Service and Privacy Policy. " +
                "If they change, we'll ask again.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Card {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("In short", style = MaterialTheme.typography.titleSmall)
                listOf(
                    "Your school owns the data it puts in. We use it only to run Timetablz for you.",
                    "Timetables are a planning aid: check them before you share them.",
                    "Some features send parts of your data to our AI provider to read rules and files.",
                    "Don't upload students' personal details; only class-level information is needed.",
                    "Paid plans are yearly and refundable for unused months.",
                ).forEach { Text("•  $it", style = MaterialTheme.typography.bodyMedium) }
            }
        }
        SecondaryButton("Read the Terms of Service", { uri.openUri("https://timetablz.com/terms") }, Modifier.fillMaxWidth())
        SecondaryButton("Read the Privacy Policy", { uri.openUri("https://timetablz.com/privacy") }, Modifier.fillMaxWidth())
        Row(Modifier.fillMaxWidth().clickable { agreed = !agreed }, verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = agreed, onCheckedChange = { agreed = it },
                colors = CheckboxDefaults.colors(checkedColor = MaterialTheme.colorScheme.primary))
            Text("I have read and agree to the Terms of Service and Privacy Policy", style = MaterialTheme.typography.bodyMedium)
        }
        ui.authError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        PrimaryButton("Continue", { session.acceptTerms() }, Modifier.fillMaxWidth(), enabled = agreed, busy = ui.authBusy == "terms")
        SecondaryButton("Sign out", { session.signOut() }, Modifier.fillMaxWidth())
    }
}

/** Google's own look for its button: white, outlined, the multicolour G. */
@Composable
private fun GoogleButton(onClick: () -> Unit, busy: Boolean, modifier: Modifier = Modifier) {
    androidx.compose.material3.OutlinedButton(
        onClick = onClick,
        enabled = !busy,
        modifier = modifier.heightIn(min = 48.dp),
        shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, com.timetablz.app.ui.theme.Slate300),
        colors = androidx.compose.material3.ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurface),
    ) {
        if (busy) {
            androidx.compose.material3.CircularProgressIndicator(strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(18.dp))
        } else {
            Text("G", fontWeight = FontWeight.Bold, color = Color(0xFF4285F4), fontSize = 18.sp)
        }
        Text("   Continue with Google", style = MaterialTheme.typography.labelLarge)
    }
}

@Composable
fun SchoolPicker(session: SessionViewModel, ui: SessionUi) {
    val uri = LocalUriHandler.current
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Choose a school", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 24.dp))
        Text("Signed in as ${ui.user?.email ?: ""}", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 8.dp))
        when {
            ui.loading -> Loading("Loading your schools…")
            ui.error != null -> {
                Text(ui.error, color = MaterialTheme.colorScheme.error)
                PrimaryButton("Try again", { session.retrySchools() }, Modifier.fillMaxWidth())
            }
            ui.schools.isEmpty() && ui.schoolsLoaded -> {
                Text(
                    "This account isn't part of a school yet. If you made your school with a different email or Google " +
                        "account, sign out and sign in with that one. Otherwise set one up on timetablz.com, or ask your " +
                        "school's admin to invite you.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                SecondaryButton("Open timetablz.com", { uri.openUri("https://timetablz.com") }, Modifier.fillMaxWidth())
            }
            !ui.schoolsLoaded -> PrimaryButton("Load my schools", { session.retrySchools() }, Modifier.fillMaxWidth())
        }
        ui.schools.forEach { s ->
            Card(onClick = { session.pick(s) }) {
                Column(Modifier.padding(16.dp)) {
                    Text(s.name, style = MaterialTheme.typography.titleMedium)
                    Text(if (s.isAdmin) "Admin" else "Viewer", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        SecondaryButton("Sign out", { session.signOut() }, Modifier.fillMaxWidth().padding(top = 16.dp))
    }
}
