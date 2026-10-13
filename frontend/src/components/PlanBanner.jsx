import { formatDate } from './BillingSection'

/**
 * A strip above the working area during a paid plan's 15-day grace period:
 * "Your Pro plan ended on X. Renew by Y to keep Pro features." After that the
 * school is locked and LockedScreen takes over; free schools see the
 * countdown in the sidebar instead (FreeCountdown).
 */
export default function PlanBanner({ entitlements, isAdmin, onRenew }) {
  if (!entitlements) return null
  const { status, paid_plan: paidPlan, plan_valid_until: validUntil, grace_ends_at: graceEnds } = entitlements
  if (!paidPlan || status !== 'grace') return null
  const name = paidPlan === 'business' ? 'Business' : 'Pro'

  const text = `Your ${name} plan ended on ${formatDate(validUntil)}. Renew by ${formatDate(graceEnds)} to keep using Timetablz without interruption.`

  return (
    <div
      role="status"
      className={`mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm ${
        'border-amber-200 bg-amber-50 text-amber-900'
      }`}
    >
      <span>{text}</span>
      {isAdmin ? (
        <button onClick={onRenew} className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700">
          Renew {name}
        </button>
      ) : (
        <span className="text-xs text-slate-500">Ask a school admin to renew.</span>
      )}
    </div>
  )
}
