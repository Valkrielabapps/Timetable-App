import { useState } from 'react'
import { motion } from 'framer-motion'

import { EVERY_PLAN, LARGE, PLANS as PRICED, detectCurrency, largeBase, largePerSection, planPrice } from '../lib/plans'

/**
 * The first step after "Get started": see the plans, then create an account.
 * Matches the landing page's look.
 *
 * Every school starts with the 14-day free trial (everything unlocked), so
 * "Start free trial" just signs up. "Buy now" signs up too and then opens
 * Settings > Plan & billing to pay (the payment needs a school). Large /
 * Group goes to the Contact page. Prices come from src/lib/plans.js.
 */
// Rupees in India, US dollars elsewhere (see detectCurrency).
function plansFor(currency) {
  return [
    ...PRICED.map((p) => ({
      id: p.id,
      name: p.name,
      price: planPrice(p, currency),
      period: '/year',
      blurb: p.sections,
      doneForYou: `Done for you: ${planPrice(p, currency, 'done_for_you')} first year`,
      features: EVERY_PLAN,
      cta: 'Start free trial',
      highlighted: p.id === 'standard',
    })),
    {
      id: 'business',
      name: LARGE.name,
      price: `From ${largeBase(currency)}`,
      period: '/year',
      blurb: LARGE.sections,
      doneForYou: `+ ${largePerSection(currency)} a year per section above ${LARGE.from}. Done for you: quoted`,
      features: [...EVERY_PLAN, 'Several schools in one account'],
      cta: 'Get in touch',
    },
  ]
}

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

// Styled exactly like the Pricing page's cards (PricingCard in
// PricingPage.jsx): Standard outlined, the button above the
// feature list, features under a divider.
function PlanCard({ plan, onChoose, delay }) {
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={fadeUp}
      transition={{ duration: 0.4, delay }}
      className={`flex flex-col rounded-2xl p-8 ${
        plan.highlighted ? 'border-2 border-neutral-900 bg-neutral-50' : 'border border-neutral-200'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <p className="text-lg font-semibold text-neutral-900">{plan.name}</p>
        {plan.highlighted && (
          <span className="rounded-full bg-neutral-900 px-2.5 py-0.5 text-[11px] font-medium text-white">Mid-size schools</span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-600">{plan.blurb}</p>

      <p className="mt-6">
        <span className="text-3xl font-semibold tracking-tight text-neutral-900">{plan.price}</span>
        {plan.period && <span className="ml-1 text-sm text-neutral-500">{plan.period}</span>}
      </p>
      {plan.doneForYou && <p className="mt-2 text-xs text-neutral-500">{plan.doneForYou}</p>}

      <button
        onClick={() => onChoose(plan.id)}
        className={`mt-6 rounded-md px-5 py-2.5 text-sm font-medium ${
          plan.highlighted ? 'bg-neutral-900 text-white hover:bg-neutral-700' : 'border border-neutral-300 text-neutral-900 hover:bg-neutral-50'
        }`}
      >
        {plan.cta}
      </button>
      {plan.id !== 'business' && (
        <button onClick={() => onChoose(plan.id, { buy: true })} className="mt-2 text-sm text-neutral-600 underline underline-offset-2 hover:text-neutral-900">
          Buy now instead
        </button>
      )}

      <ul className="mt-8 space-y-3 border-t border-neutral-200 pt-6">
        {plan.features.map((f) => (
          <li key={f} className="flex items-start gap-2.5 text-sm text-neutral-700">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0 text-neutral-500" aria-hidden="true">
              <path d="M20 6 9 17l-5-5" />
            </svg>
            {f}
          </li>
        ))}
      </ul>
    </motion.div>
  )
}

export default function PlanPicker({ onChoose, onBack, onSignIn }) {
  const [currency] = useState(detectCurrency)
  const PLANS = plansFor(currency)
  return (
    <div className="min-h-screen bg-white text-neutral-900">
      <div className="sticky top-0 z-30 border-b border-white/10 bg-black">
        <div className="flex items-center px-8 py-4 md:px-16 lg:px-28">
          <button onClick={onBack} className="text-[19px] font-bold tracking-tight text-white">
            Timetablz
          </button>
          <div className="ml-auto flex items-center gap-6">
            <button onClick={onSignIn} className="text-[15px] font-medium text-neutral-300 hover:text-white">
              Sign in
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-16">
        <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.5 }}>
          <h1 className="font-serif text-4xl font-medium tracking-tight text-neutral-900 md:text-5xl">
            Choose how you want to start
          </h1>
          <p className="mt-4 max-w-xl text-neutral-600">
            Every plan starts with 14 days free, everything unlocked, no card needed. Plans are priced by the number
            of sections in your school; choose one whenever you&rsquo;re ready.
          </p>
        </motion.div>

        <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {PLANS.map((plan, i) => (
            <PlanCard key={plan.id} plan={plan} onChoose={onChoose} delay={i * 0.08} />
          ))}
        </div>

        <p className="mt-8 text-sm text-neutral-500">
          After 14 days the school is paused until you choose a plan. Nothing you&rsquo;ve set up is deleted.
          {currency === 'USD' && ' Prices outside India are in US dollars, and we invoice you by email.'}
        </p>
      </div>
    </div>
  )
}
