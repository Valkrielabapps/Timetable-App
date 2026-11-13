package com.timetablz.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.timetablz.app.data.ApiException
import com.timetablz.app.data.School
import com.timetablz.app.ui.theme.Ink
import com.timetablz.app.ui.theme.Red600
import com.timetablz.app.ui.theme.Slate500
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(state: AppState) {
    val scope = rememberCoroutineScope()
    val uri = LocalUriHandler.current
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun submit() {
        if (email.isBlank() || password.isEmpty() || busy) return
        busy = true
        error = null
        scope.launch {
            try {
                state.signIn(email, password)
            } catch (e: ApiException) {
                error = e.message
            } finally {
                busy = false
            }
        }
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
        Text("Timetablz", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Ink)
        Text("Sign in with your Timetablz account", style = MaterialTheme.typography.bodyLarge, color = Slate500)
        OutlinedTextField(
            value = email, onValueChange = { email = it }, label = { Text("Email") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
        )
        OutlinedTextField(
            value = password, onValueChange = { password = it }, label = { Text("Password") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { submit() }),
            modifier = Modifier.fillMaxWidth(),
        )
        error?.let { Text(it, color = Red600, style = MaterialTheme.typography.bodyMedium) }
        PrimaryButton("Sign in", ::submit, Modifier.fillMaxWidth(), enabled = email.isNotBlank() && password.isNotEmpty(), busy = busy)
        Text(
            "Forgot your password, or signed up with Google? Reset it on timetablz.com.",
            style = MaterialTheme.typography.bodySmall, color = Slate500,
        )
        SecondaryButton("Open timetablz.com", { uri.openUri("https://timetablz.com") }, Modifier.fillMaxWidth())
    }
}

@Composable
fun TermsScreen(state: AppState) {
    val scope = rememberCoroutineScope()
    val uri = LocalUriHandler.current
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Before you carry on", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 24.dp))
        Text(
            "Please read and accept the Terms of Service and Privacy Policy. They cover how Timetablz handles your " +
                "school's data.",
            color = Slate500,
        )
        SecondaryButton("Read the Terms of Service", { uri.openUri("https://timetablz.com/terms") }, Modifier.fillMaxWidth())
        SecondaryButton("Read the Privacy Policy", { uri.openUri("https://timetablz.com/privacy") }, Modifier.fillMaxWidth())
        error?.let { Text(it, color = Red600) }
        PrimaryButton("I agree", {
            busy = true
            scope.launch {
                try { state.acceptTerms() } catch (e: ApiException) { error = e.message } finally { busy = false }
            }
        }, Modifier.fillMaxWidth(), busy = busy)
        SecondaryButton("Sign out", { state.signOut() }, Modifier.fillMaxWidth())
    }
}

@Composable
fun SchoolPicker(state: AppState) {
    val scope = rememberCoroutineScope()
    val uri = LocalUriHandler.current
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Choose a school", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 24.dp, bottom = 8.dp))
        if (state.schools.isEmpty()) {
            Text("Your account isn't part of a school yet. Set one up on timetablz.com, or ask your school's admin to invite you.", color = Slate500)
            SecondaryButton("Open timetablz.com", { uri.openUri("https://timetablz.com") }, Modifier.fillMaxWidth())
        }
        state.schools.forEach { s: School ->
            Card(onClick = { scope.launch { state.pick(s) } }) {
                Column(Modifier.padding(16.dp)) {
                    Text(s.name, style = MaterialTheme.typography.titleMedium)
                    Text(if (s.isAdmin) "Admin" else "Viewer", style = MaterialTheme.typography.bodySmall, color = Slate500)
                }
            }
        }
        state.error?.let { Text(it, color = Red600) }
        SecondaryButton("Sign out", { state.signOut() }, Modifier.fillMaxWidth().padding(top = 16.dp))
    }
}
