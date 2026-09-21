import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api, setToken } from '../api'

// Set by whoever deploys this (see docs/DEPLOYMENT.md) after creating a
// Google Cloud OAuth 2.0 Client ID. Left blank in local dev by default —
// the button below simply doesn't render when it's unset, rather than
// showing a broken "Sign in with Google" that fails on click.
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID

/**
 * Login / signup screen. Email+password is fully functional. Google
 * sign-in uses Google Identity Services' hosted button (loaded from
 * accounts.google.com at runtime, not bundled) rather than a hand-built
 * button — Google requires their own rendered button/prompt for the ID
 * token flow used here, so this isn't stylistic, it's how the flow works.
 * The resulting ID token is verified server-side in
 * backend/app/routers/auth.py's /auth/google endpoint, never trusted
 * as-is from the client.
 */
export default function AuthPage({ onAuthenticated, onBack }) {
  const [mode, setMode] = useState('login') // 'login' | 'signup' | 'forgot'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  // True once a forgot-password request has been submitted — shown
  // instead of the form so a resubmit can't fire twice. Deliberately the
  // same message regardless of what the backend actually did (see
  // forgot_password's docstring in backend/app/routers/auth.py): this
  // screen must not reveal whether the email had an account.
  const [forgotSubmitted, setForgotSubmitted] = useState(false)
  // True if the Google script failed to load (offline, ad-blocker,
  // accounts.google.com unreachable, etc.) — without this, that failure
  // was silent: the "or" divider would render with no button ever
  // appearing beneath it, and no indication anything had gone wrong.
  const [googleUnavailable, setGoogleUnavailable] = useState(false)
  const googleButtonRef = useRef(null)

  const isLogin = mode === 'login'

  async function handleGoogleCredential(response) {
    setError(null)
    setLoading(true)
    try {
      const result = await api.loginWithGoogle(response.credential)
      setToken(result.access_token)
      onAuthenticated(result.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Loads Google's script once, initializes it with our client ID, and
  // renders its button into googleButtonRef. Skipped entirely if no
  // client ID is configured — see GOOGLE_CLIENT_ID above.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return

    let cancelled = false

    function render() {
      if (cancelled || !window.google || !googleButtonRef.current) return
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: handleGoogleCredential,
      })
      window.google.accounts.id.renderButton(googleButtonRef.current, {
        theme: 'outline',
        size: 'large',
        width: 328,
        text: 'continue_with',
      })
    }

    if (window.google?.accounts?.id) {
      render()
    } else {
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.onload = render
      script.onerror = () => {
        if (!cancelled) setGoogleUnavailable(true)
      }
      document.head.appendChild(script)
    }

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const result = isLogin
        ? await api.login({ email, password })
        : await api.signup({ email, password, name: name || null })
      setToken(result.access_token)
      onAuthenticated(result.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleForgotSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await api.forgotPassword(email)
      setForgotSubmitted(true)
    } catch (err) {
      // Only a genuinely broken request (network error, malformed email)
      // reaches here — the backend itself always returns success-shaped
      // 202 regardless of whether the email has an account, so this
      // isn't the "no account found" path.
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-8">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm"
      >
        <div className="mb-6 text-center">
          {onBack ? (
            <button
              onClick={onBack}
              className="mb-3 text-sm font-semibold text-slate-900 hover:text-slate-600"
            >
              ← Timetable
            </button>
          ) : (
            <div className="text-lg font-semibold text-slate-900">Timetable</div>
          )}
          <h1 className="mt-2 text-2xl font-semibold">
            {mode === 'forgot' ? 'Reset your password' : isLogin ? 'Welcome back' : 'Create your account'}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {mode === 'forgot'
              ? "Enter your account's email and we'll send you a reset link"
              : isLogin
                ? "Sign in to manage your school's timetables"
                : 'Set up your school in a couple of minutes'}
          </p>
        </div>

        {mode === 'forgot' ? (
          forgotSubmitted ? (
            <div className="rounded-md bg-slate-50 p-4 text-center text-sm text-slate-600">
              If an account exists for {email}, we've sent a password reset link to it.
              <button
                type="button"
                onClick={() => {
                  setMode('login')
                  setForgotSubmitted(false)
                }}
                className="mt-3 block w-full text-neutral-900 underline underline-offset-2 hover:text-neutral-600"
              >
                Back to sign in
              </button>
            </div>
          ) : (
            <form onSubmit={handleForgotSubmit} className="flex flex-col gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@school.edu"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
                />
              </div>

              <AnimatePresence>
                {error && (
                  <motion.p
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.15 }}
                    className="overflow-hidden text-sm text-red-600"
                  >
                    {error}
                  </motion.p>
                )}
              </AnimatePresence>

              <motion.button
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
                type="submit"
                disabled={loading}
                className="mt-1 rounded-md bg-neutral-900 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
              >
                {loading ? 'Sending…' : 'Send reset link'}
              </motion.button>
              <button
                type="button"
                onClick={() => setMode('login')}
                className="text-center text-sm text-neutral-900 underline underline-offset-2 hover:text-neutral-600"
              >
                Back to sign in
              </button>
            </form>
          )
        ) : (
          <>
            {GOOGLE_CLIENT_ID ? (
              <>
                {googleUnavailable ? (
                  <p className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    Couldn't load Google sign-in (check your connection) — email and password still
                    work below.
                  </p>
                ) : (
                  <div className="mb-4 flex justify-center" ref={googleButtonRef} />
                )}
                <div className="mb-4 flex items-center gap-3 text-xs uppercase tracking-wide text-slate-500">
                  <div className="h-px flex-1 bg-slate-200" />
                  or
                  <div className="h-px flex-1 bg-slate-200" />
                </div>
              </>
            ) : null}

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <AnimatePresence initial={false}>
            {!isLogin && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.18, ease: 'easeOut' }}
                className="overflow-hidden"
              >
                <label className="mb-1 block text-xs font-medium text-slate-500">Name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
                />
              </motion.div>
            )}
          </AnimatePresence>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@school.edu"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />
            {isLogin && (
              <button
                type="button"
                onClick={() => {
                  setMode('forgot')
                  setError(null)
                }}
                className="mt-1 text-xs text-neutral-900 underline underline-offset-2 hover:text-neutral-600"
              >
                Forgot password?
              </button>
            )}
          </div>

          <AnimatePresence>
            {error && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.15 }}
                className="overflow-hidden text-sm text-red-600"
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>

          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            disabled={loading}
            className="mt-1 rounded-md bg-neutral-900 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {loading ? 'Please wait…' : isLogin ? 'Sign in' : 'Create account'}
          </motion.button>
        </form>

        <p className="mt-4 text-center text-sm">
          {isLogin ? "Don't have an account? " : 'Already have an account? '}
          <button
            type="button"
            onClick={() => setMode(isLogin ? 'signup' : 'login')}
            className="text-neutral-900 underline underline-offset-2 hover:text-neutral-600"
          >
            {isLogin ? 'Sign up' : 'Sign in'}
          </button>
        </p>
          </>
        )}
      </motion.div>
    </div>
  )
}
