import { useState } from 'react'
import { api, setToken } from '../api'

/**
 * Landing screen for a password-reset link. Same query-param routing
 * pattern as AcceptInvitePage.jsx (no client-side router in this app):
 * the link is `?reset=<token>`, checked by App.jsx before the normal
 * login/app shell renders, regardless of whether the visitor is already
 * logged in elsewhere — see backend/app/routers/auth.py's reset_password
 * endpoint, which just needs a valid unexpired/unused token, not an
 * existing session.
 *
 * Unlike AcceptInvitePage there's no preview step (nothing to fetch and
 * show before submitting — the backend doesn't expose whether a given
 * reset token is valid except by trying to use it), so this goes
 * straight to the "set a new password" form.
 */
export default function ResetPasswordPage({ token, onReset }) {
  const [newPassword, setNewPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const result = await api.resetPassword(token, newPassword)
      setToken(result.access_token)
      onReset(result.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-8">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 text-center">
          <div className="text-lg font-semibold text-slate-900">Timetable</div>
          <h1 className="mt-2 text-2xl font-semibold">Set a new password</h1>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">New password</label>
            <input
              type="password"
              required
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600">
              {error} — request a new reset link from the sign-in page and try again.
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="mt-1 rounded-md bg-neutral-900 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {submitting ? 'Resetting…' : 'Reset password'}
          </button>
        </form>
      </div>
    </div>
  )
}
