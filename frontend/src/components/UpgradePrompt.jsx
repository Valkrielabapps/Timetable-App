import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

/**
 * Appears whenever the backend refuses something because of the school's
 * plan (HTTP 402, see api.js). The message comes from the backend as-is,
 * e.g. "The Free plan includes up to 5 sections. Upgrade to Pro ...", so
 * every limit in the app gets the same prompt without each screen having to
 * know about plans.
 */
export default function UpgradePrompt({ isAdmin, onSeePlans }) {
  const [message, setMessage] = useState(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    function onLimit(e) {
      setMessage(e.detail?.message || 'This needs a higher plan.')
      // Usage numbers on the billing page are now out of date.
      queryClient.invalidateQueries({ queryKey: ['entitlements'] })
    }
    window.addEventListener('timetablz:plan-limit', onLimit)
    return () => window.removeEventListener('timetablz:plan-limit', onLimit)
  }, [queryClient])

  useEffect(() => {
    if (!message) return undefined
    const onKey = (e) => e.key === 'Escape' && setMessage(null)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [message])

  if (!message) return null
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-neutral-900/40" onMouseDown={() => setMessage(null)} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-labelledby="upgrade-title" className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
        <h2 id="upgrade-title" className="text-base font-semibold text-neutral-900">You&rsquo;ve reached your plan&rsquo;s limit</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{message}</p>
        {!isAdmin && <p className="mt-2 text-sm text-slate-500">Ask a school admin to upgrade.</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={() => setMessage(null)} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Not now
          </button>
          <button
            onClick={() => {
              setMessage(null)
              onSeePlans()
            }}
            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
          >
            See plans
          </button>
        </div>
      </div>
    </div>
  )
}
