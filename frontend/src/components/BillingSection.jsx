import { useState } from 'react'
import { startCheckout } from '../payments'
import { useEntitlements } from '../hooks/useEntitlements'

const FALLBACK_PRO_PRICE = 4999

// The API sends UTC timestamps without a zone suffix.
export function parseUtc(value) {
  if (!value) return null
  return new Date(/([zZ]|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`)
}

export function formatDate(value) {
  const date = parseUtc(value)
  return date ? date.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) : ''
}

const PLAN_NAMES = { free: 'Free', pro: 'Pro', business: 'Business' }

/**
 * Settings > Plan & billing: the school's plan, where it is in its year
 * (active / grace / expired), how much of each limit is used, and - for
 * admins - Pay now / Renew through Cashfree checkout.
 *
 * Everything shown comes from GET /api/schools/{id}/entitlements, which reads
 * the same plan definitions the backend enforces, so the numbers here are
 * the real limits. The plan only changes after the backend has confirmed a
 * payment with Cashfree.
 */
export default function BillingSection({ school, isAdmin }) {
  const { data: ent, isLoading } = useEntitlements(school?.id)
  const defaultPhone = school?.profile?.phone ?? ''
  const [phone, setPhone] = useState(defaultPhone)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const price = ent?.pro_price_inr ?? FALLBACK_PRO_PRICE
  const priceText = `₹${price.toLocaleString('en-IN')}`
  const status = ent?.status ?? 'free'
  const paidPlan = ent?.paid_plan
  const onBusiness = paidPlan === 'business' && status !== 'locked'
  const renewing = paidPlan === 'pro'

  async function handlePay(e) {
    e.preventDefault()
    setError(null)
    const digits = phone.replace(/[\s\-()]/g, '').replace(/^\+?91(?=\d{10}$)/, '').replace(/^0(?=\d{10}$)/, '')
    if (!/^[6-9]\d{9}$/.test(digits)) {
      setError('Enter a valid 10-digit mobile number. Cashfree needs one for every payment.')
      return
    }
    setBusy(true)
    try {
      await startCheckout({ schoolId: school.id, phone: digits })
      // _self: the browser is leaving for Cashfree. _modal: we've navigated
      // to the status page. Either way there's nothing more to do here.
    } catch (err) {
      setError(err.message || 'Could not start the payment. Please try again.')
      setBusy(false)
    }
  }

  const statusLine = {
    free: ent?.free_days_left != null
      ? `${ent.free_days_left} ${ent.free_days_left === 1 ? 'day' : 'days'} left of your 14 free days`
      : null,
    locked: paidPlan
      ? `Your ${PLAN_NAMES[paidPlan] ?? 'paid'} plan has ended. Renew to unlock the school.`
      : 'Your 14 free days are over. Upgrade to unlock the school.',
    active: ent?.plan_valid_until ? `Active until ${formatDate(ent.plan_valid_until)}` : 'Active',
    grace: `Ended on ${formatDate(ent?.plan_valid_until)}. ${PLAN_NAMES[paidPlan] ?? 'Paid'} features stay on until ${formatDate(ent?.grace_ends_at)}.`,
  }[status]

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h3 className="text-base font-semibold">Plan &amp; billing</h3>
      <p className="mt-1 text-sm text-slate-500">Your school&rsquo;s plan and what it includes.</p>

      <div
        className={`mt-5 rounded-lg border px-5 py-4 ${
          status === 'grace' || status === 'locked' ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-slate-50'
        }`}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <p className="text-sm text-slate-500">Current plan</p>
            <p className="mt-0.5 text-lg font-semibold">
              {isLoading ? '…' : status === 'locked' ? 'Paused' : PLAN_NAMES[ent?.plan] ?? 'Free'}
            </p>
          </div>
          {statusLine && <p className="text-sm text-slate-600">{statusLine}</p>}
        </div>

        {ent && (
          <dl className="mt-4 grid gap-3 sm:grid-cols-3">
            <Usage label="Sections" used={ent.usage.sections} limit={ent.limits.max_sections} />
            <Usage label="People with access" used={ent.usage.members} limit={ent.limits.max_members} />
            <Usage
              label="AI actions this month"
              used={ent.usage.ai_actions_this_month}
              limit={ent.limits.ai_actions_per_month}
            />
          </dl>
        )}
      </div>

      {onBusiness ? (
        <p className="mt-5 text-sm text-slate-500">
          Your school is on a Business plan. For changes, write to{' '}
          <a className="underline" href="mailto:support@timetablz.com">support@timetablz.com</a>.
        </p>
      ) : isAdmin ? (
        <form onSubmit={handlePay} className="mt-6 flex flex-col gap-4">
          <div>
            <p className="text-sm font-medium text-slate-900">{renewing ? 'Renew Pro for a year' : 'Upgrade to Pro'}</p>
            <p className="mt-1 text-sm text-slate-500">
              {priceText} for one year.{' '}
              {renewing && status === 'active'
                ? 'The new year starts when your current one ends, so renewing early loses nothing.'
                : 'Up to 60 sections, up to 5 people, every AI feature, and clean exports.'}
            </p>
          </div>
          <label className="flex max-w-xs flex-col gap-1">
            <span className="text-xs font-medium text-slate-500">Mobile number for the payment receipt</span>
            <input
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="98765 43210"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div>
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-60"
            >
              {busy ? 'Opening secure checkout…' : `${renewing ? 'Renew now' : 'Pay now'} · ${priceText}`}
            </button>
            <p className="mt-2 text-xs text-slate-400">
              Payments are processed securely by Cashfree. Need more than 60 sections or several schools?{' '}
              <a className="underline" href="?page=contact">Contact us about Business</a>.
            </p>
          </div>
        </form>
      ) : (
        <p className="mt-5 text-sm text-slate-500">Only a school admin can change the plan.</p>
      )}
    </section>
  )
}

function Usage({ label, used, limit }) {
  const unlimited = limit == null
  const pct = unlimited || !limit ? 0 : Math.min(100, Math.round((used / limit) * 100))
  const full = !unlimited && used >= limit
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className={`mt-0.5 text-sm font-medium ${full ? 'text-red-600' : 'text-slate-900'}`}>
        {used}
        {unlimited ? <span className="font-normal text-slate-400"> · unlimited</span> : ` / ${limit}`}
      </dd>
      {!unlimited && (
        <div className="mt-1 h-1.5 w-full rounded-full bg-slate-200" aria-hidden="true">
          <div className={`h-1.5 rounded-full ${full ? 'bg-red-500' : 'bg-neutral-900'}`} style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}
