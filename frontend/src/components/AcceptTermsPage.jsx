import { useState } from 'react'
import { api } from '../api'
import { renderMarkdown } from './LegalPage'
import terms from '../legal/terms-of-service.md?raw'

/**
 * Shown after sign-in until the person accepts the current Terms of Service
 * and Privacy Policy: at their first sign-in, and again whenever the terms
 * change (backend/app/core/terms.py). Nothing else in the app is reachable
 * until they agree or sign out. The backend records each acceptance with the
 * time, IP address and browser.
 */
export default function AcceptTermsPage({ user, onAccepted, onSignOut }) {
  const [agreed, setAgreed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const updated = user.terms_version && user.has_accepted_before

  async function accept() {
    setSaving(true)
    setError(null)
    try {
      onAccepted(await api.acceptTerms(user.terms_version))
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <section
        aria-label="Accept the Terms of Service"
        className="flex max-h-[92vh] w-full max-w-2xl flex-col rounded-xl border border-slate-200 bg-white shadow-sm"
      >
        <header className="border-b border-slate-200 px-6 py-4">
          <h1 className="text-lg font-semibold text-slate-900">
            {updated ? 'We’ve updated our terms' : 'Before you continue'}
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Please read and accept the Timetablz Terms of Service and Privacy Policy to use the app.
          </p>
        </header>

        <div
          tabIndex={0}
          aria-label="Terms of Service"
          className="min-h-0 flex-1 overflow-y-auto px-6 py-4 text-sm leading-relaxed text-slate-700"
        >
          {renderMarkdown(terms)}
        </div>

        <footer className="border-t border-slate-200 px-6 py-4">
          <p className="text-xs text-slate-500">
            Also read our{' '}
            <a href="/privacy" target="_blank" rel="noreferrer" className="underline hover:text-slate-700">
              Privacy Policy
            </a>{' '}
            and{' '}
            <a href="/refunds" target="_blank" rel="noreferrer" className="underline hover:text-slate-700">
              Refund and Cancellation Policy
            </a>
            .
          </p>
          <label className="mt-3 flex cursor-pointer items-start gap-2 text-sm text-slate-800">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
            />
            <span>
              I have read and agree to the Terms of Service and Privacy Policy, and I am authorised to accept them
              for my school or institution.
            </span>
          </label>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={accept}
              disabled={!agreed || saving}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'I agree, continue'}
            </button>
            <button
              type="button"
              onClick={onSignOut}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Sign out
            </button>
            <span className="ml-auto text-xs text-slate-500">Signed in as {user.email} · Version {user.terms_version}</span>
          </div>
        </footer>
      </section>
    </div>
  )
}
