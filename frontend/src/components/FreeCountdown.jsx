/**
 * Bottom of the sidebar while a school is in its 14 free days:
 * "Free plan · 9 days left" with a small bar and an Upgrade button.
 */
export default function FreeCountdown({ entitlements, onUpgrade }) {
  if (!entitlements || entitlements.status !== 'free' || entitlements.free_days_left == null) return null
  const left = entitlements.free_days_left
  const total = 14
  const pct = Math.max(0, Math.min(100, Math.round((left / total) * 100)))
  const urgent = left <= 3
  return (
    <div className={`rounded-lg border px-3 py-2.5 ${urgent ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-slate-50'}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-slate-500">Free plan</span>
        <span className={`text-sm font-semibold ${urgent ? 'text-amber-800' : 'text-slate-900'}`} aria-live="polite">
          {left} {left === 1 ? 'day' : 'days'} left
        </span>
      </div>
      <div className="mt-1.5 h-1.5 w-full rounded-full bg-slate-200" aria-hidden="true">
        <div className={`h-1.5 rounded-full ${urgent ? 'bg-amber-500' : 'bg-neutral-900'}`} style={{ width: `${pct}%` }} />
      </div>
      <button onClick={onUpgrade} className="mt-2 text-xs font-medium text-neutral-900 underline underline-offset-2 hover:text-neutral-600">
        Upgrade to Pro
      </button>
    </div>
  )
}
