/**
 * Shown in place of every working tab once a school is locked: its 14 free
 * days are over without a payment, or a paid plan's 15-day grace period has
 * ended (backend app/services/plans.py). Settings stays reachable, since
 * Plan & billing is how the school unlocks.
 */
import { PLANS, PLAN_NAMES, detectCurrency, planPrice } from '../lib/plans'

export default function LockedScreen({ entitlements, isAdmin, onUpgrade }) {
  const from = planPrice(PLANS[0], detectCurrency())
  const paid = entitlements?.paid_plan
  const title = paid ? `Your ${PLAN_NAMES[paid] ?? 'paid'} plan has ended` : 'Your 14-day free trial has ended'
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-700" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="5" y="11" width="14" height="10" rx="2" />
            <path d="M8 11V7a4 4 0 0 1 8 0v4" />
          </svg>
        </div>
        <h2 className="mt-5 text-xl font-semibold">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          Choose a plan to keep building and editing timetables. Plans start at {from} a year, priced by the number
          of sections. Everything you&rsquo;ve set up is saved and comes straight back the moment you pay.
        </p>
        {isAdmin ? (
          <button
            onClick={onUpgrade}
            className="mt-6 rounded-lg bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700"
          >
            {paid ? 'Renew your plan' : 'Choose a plan'}
          </button>
        ) : (
          <p className="mt-6 text-sm text-slate-500">Ask a school admin to choose a plan.</p>
        )}
        <p className="mt-4 text-xs text-slate-400">
          Questions? <a className="underline" href="mailto:support@timetablz.com">support@timetablz.com</a>
        </p>
      </div>
    </div>
  )
}
