/**
 * Error tracking (Sentry) for the browser.
 *
 * Mirrors backend/app/core/observability.py: entirely optional, and a missing
 * DSN is the supported default rather than a misconfiguration. With no
 * VITE_SENTRY_DSN set, initSentry() returns without loading anything and the
 * ErrorBoundary in App.jsx still works - it just renders the fallback without
 * reporting anywhere.
 *
 * Note that VITE_ vars are inlined at build time, so changing the DSN in
 * Vercel requires a redeploy, not just a save (same as VITE_GOOGLE_CLIENT_ID).
 */
import * as Sentry from '@sentry/react'

const DSN = import.meta.env.VITE_SENTRY_DSN

export function initSentry() {
  if (!DSN) return false

  Sentry.init({
    dsn: DSN,
    environment: import.meta.env.MODE,
    // Never attach IP addresses or other identifiers Sentry would otherwise
    // infer. This app is used by school staff; a crash report should say what
    // broke, not who was using it.
    sendDefaultPii: false,
    // Errors only. Performance traces consume the same free-tier quota, and
    // nothing here is slow enough on the frontend to justify spending it.
    tracesSampleRate: 0,
    beforeSend(event) {
      // The JWT lives in localStorage and can end up in a URL during the
      // invite/reset flows, so strip anything token-shaped from the URL
      // before the event leaves the browser.
      if (event.request?.url) {
        event.request.url = event.request.url.replace(
          /([?&](token|access_token|jwt)=)[^&]*/gi,
          '$1[scrubbed]',
        )
      }
      return event
    },
  })
  return true
}

export const ErrorBoundary = Sentry.ErrorBoundary
