import { useState } from 'react'
import { startCheckout } from '../payments'

const PRO_PRICE = 4999

// The API sends UTC timestamps without a zone suffix.
export function parseUtc(value) {
  if (!value) return null
  return new Date(/([zZ]|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`)
}

export function formatDate(value) {
  const date = parseUtc(value)
  return date ? date.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) : ''
}

/**
 * Settings > Plan & billing. Shows the school's plan and, for admins, a
 * "Pay now" button that opens Cashfree checkout for a year of Pro.
 *
 * The plan shown here comes from the school record, which only changes after
 * the backend has confirmed a payment with Cashfree - so this never claims a
 * plan the school hasn't actually paid for.
 */
export default function BillingSection({ school, isAdmin }) {
  const defaultPhone = school?.profile?.phone ?? ''
  const [phone, setPhone] = useState(defaultPhone)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const validUntil = school?.plan_valid_until
  const isPro = school?.plan === 'pro' && parseUtc(validUntil) > new Date()

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

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h3 className="text-base font-semibold">Plan &amp; billing</h3>
      <p className="mt-1 text-sm text-slate-500">Your school&rsquo;s current plan.</p>

      <div className="mt-5 flex flex-wrap items-baseline justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-5 py-4">
        <div>
          <p className="text-sm text-slate-500">Current plan</p>
          <p className="mt-0.5 text-lg font-semibold">{isPro ? 'Pro' : 'Free'}</p>
        </div>
        {isPro && <p className="text-sm text-slate-600">Active until {formatDate(validUntil)}</p>}
      </div>

      {isAdmin ? (
        <form onSubmit={handlePay} className="mt-6 flex flex-col gap-4">
          <div>
            <p className="text-sm font-medium text-slate-900">
              {isPro ? 'Renew Pro for another year' : 'Upgrade to Pro'}
            </p>
            <p className="mt-1 text-sm text-slate-500">
              ₹{PRO_PRICE.toLocaleString('en-IN')} for one year. {isPro ? 'The year is added on after your current one ends.' : 'Up to 500 students, AI help with setup and rules, priority support.'}
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
              {busy ? 'Opening secure checkout…' : `Pay now · ₹${PRO_PRICE.toLocaleString('en-IN')}`}
            </button>
            <p className="mt-2 text-xs text-slate-400">Payments are processed securely by Cashfree.</p>
          </div>
        </form>
      ) : (
        <p className="mt-5 text-sm text-slate-500">Only a school admin can change the plan.</p>
      )}
    </section>
  )
}
