import { useEffect, useState } from 'react'
import { api, setToken } from '../api'

/**
 * Landing screen for an invite link. This app has no client-side router
 * (see App.jsx — it's plain tab state, no react-router), so the invite
 * link is a query param instead of a path: `?invite=<token>`. App.jsx
 * checks for that param before anything else and renders this in place
 * of the normal login/app shell, regardless of whether the visitor is
 * already logged in — accepting an invite for a *different* school than
 * whatever they're currently logged into as is a legitimate thing to do
 * (see backend/app/routers/invites.py: accepting always requires a
 * password, so this can't be used to silently switch who's logged in).
 *
 * `token` comes from App.jsx; `onAccepted(user, accessToken)` is called
 * on success so App.jsx can log the visitor in and clear the query param.
 */
export default function AcceptInvitePage({ token, onAccepted }) {
  const [preview, setPreview] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    api.previewInvite(token).then(setPreview).catch((err) => setLoadError(err.message))
  }, [token])

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitError(null)
    setSubmitting(true)
    try {
      const result = await api.acceptInvite(token, { name: name || null, password })
      setToken(result.access_token)
      onAccepted(result.user)
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-8">
        <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 text-center shadow-sm">
          <p className="text-sm text-red-600">
            This invite link is invalid, expired, or has already been used.
          </p>
        </div>
      </div>
    )
  }

  if (!preview) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-8">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 text-center">
          <div className="text-lg font-semibold text-slate-900">Timetable</div>
          <h1 className="mt-2 text-2xl font-semibold">Join {preview.school_name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {preview.email} was invited as {preview.role === 'admin' ? 'an admin' : 'a viewer'}.
          </p>
        </div>

        {preview.status !== 'pending' ? (
          <p className="text-center text-sm text-slate-500">
            This invite has already been used or was revoked.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                Your name (only needed if you're new here)
              </label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                Password
              </label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Set a new password, or enter your existing one"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
              />
            </div>

            {submitError && <p className="text-sm text-red-600">{submitError}</p>}

            <button
              type="submit"
              disabled={submitting}
              className="mt-1 rounded-md bg-neutral-900 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {submitting ? 'Joining…' : 'Accept invite'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
