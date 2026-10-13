import { formatDate } from './BillingSection'

/**
 * A strip above the working area when a paid plan is ending or has ended:
 *   grace   - "Your Pro plan ended on X. Renew by Y to keep Pro features."
 *   expired - "Your Pro plan has ended; this school is on Free limits."
 * Nothing for free schools that never paid, or for active plans.
 */
export default function PlanBanner({ entitlements, isAdmin, onRenew }) {
  if (!entitlements) return null
  const { status, paid_plan: paidPlan, plan_valid_until: validUntil, grace_ends_at: graceEnds } = entitlements
  if (!paidPlan || (status !== 'grace' && status !== 'expired')) return null
  const name = paidPlan === 'business' ? 'Business' : 'Pro'

  const text =
    status === 'grace'
      ? `Your ${name} plan ended on ${formatDate(validUntil)}. Renew by ${formatDate(graceEnds)} to keep ${name} features.`
      : `Your ${name} plan has ended, so this school is back on the Free plan's limits. Nothing has been deleted.`

  return (
    <div
      role="status"
      className={`mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm ${
        status === 'grace' ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-slate-200 bg-white text-slate-700'
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
