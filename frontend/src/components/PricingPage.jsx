import { useState } from 'react'
import { motion } from 'framer-motion'

/**
 * Standalone pricing page, modeled on the Papermark pricing page — reached
 * via `?page=pricing` (see App.jsx, same no-router pattern as
 * PrivacyPolicyPage/TermsOfServicePage) rather than the old in-page
 * `#pricing` anchor, since LandingPage.jsx's Pricing() section was
 * removed from the homepage by request.
 *
 * Deliberately terse compared to the first version of this page: each
 * card lists ~5 highlights rather than a full feature-comparison matrix
 * (explicit "don't reveal everything yet" request) — see FEATURE_BULLETS
 * below instead of a FEATURE_MATRIX. Also renamed Starter/Growth/Group to
 * Free/Pro/Business per that same request.
 *
 * Still left out, same reasoning as before:
 *   - The top logo strip / "70,000+ companies" trust line — no comparable
 *     customer count exists (see TrustBar/MetricsSection on the homepage).
 *   - The Monthly/Annual billing toggle — annual pricing hasn't been
 *     decided.
 *   - The "View Github / self-hosted" half of the closing banner — no
 *     public repo or self-hosted offering exists.
 *   - The orange accent color — kept to the site's established black/
 *     white/grey theme.
 *
 * The USD/INR toggle IS new here (explicit request) — see USD_PER_INR
 * below on what it does and doesn't represent.
 */

// Rough, clearly-labeled reference rate for *display* only — this does
// NOT mean Pro is separately priced in USD, or that a foreign school
// would actually be billed in dollars today (Razorpay billing is INR —
// see the business-setup conversation). It just converts the one real
// price (₹4,999) so a visitor thinking in USD has a ballpark figure,
// same as any "approx. $X" conversion widget. Update this if the real
// rate drifts far enough that $60 stops being a fair approximation.
const USD_PER_INR = 1 / 83

const PRICING_TIERS = [
  {
    name: 'Free',
    priceInr: 0,
    tagline: 'Try it out with your first section',
    highlights: ['1 school', 'Up to 100 students', 'Unlimited timetables', 'Email support'],
    highlighted: false,
    ctaLabel: 'Get started free',
  },
  {
    name: 'Pro',
    priceInr: 4999,
    period: '+ GST /month',
    tagline: 'For a school that needs more room to grow',
    highlights: ['Everything in Free, plus:', 'Up to 500 students', 'AI-assisted setup & constraints', 'Priority support'],
    highlighted: true,
    ctaLabel: 'Get started',
  },
  {
    name: 'Business',
    priceInr: null,
    tagline: 'For a group running several schools',
    highlights: ['Everything in Pro, plus:', 'Multiple schools', 'Dedicated onboarding', 'Custom terms'],
    highlighted: false,
    ctaLabel: 'Get in touch',
  },
]

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

function formatPrice(priceInr, currency) {
  if (priceInr === null) return 'Custom'
  if (priceInr === 0) return currency === 'USD' ? '$0' : '₹0'
  if (currency === 'USD') {
    return `$${Math.round(priceInr * USD_PER_INR)}`
  }
  return `₹${priceInr.toLocaleString('en-IN')}`
}

export default function PricingPage({ onBack, onGetStarted }) {
  const [currency, setCurrency] = useState('INR')

  return (
    <div className="min-h-screen bg-white">
      <div className="sticky top-0 z-30 border-b border-neutral-100 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <button onClick={onBack} className="text-[17px] font-bold tracking-tight text-neutral-900">
            Timetablz
          </button>
          <div className="flex items-center gap-5">
            <button onClick={onBack} className="text-sm font-medium text-neutral-500 hover:text-neutral-900">
              ← Back to home
            </button>
            <button
              onClick={onGetStarted}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
            >
              Get started free
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-16">
        <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.5 }}>
          <h1 className="font-serif text-4xl font-medium tracking-tight text-neutral-900 md:text-5xl">
            Find the plan that works for your school
          </h1>
          <p className="mt-4 max-w-xl text-neutral-500">
            Every plan includes <strong className="text-neutral-700">unlimited timetables</strong>,{' '}
            <strong className="text-neutral-700">conflict-free generation</strong>, and{' '}
            <strong className="text-neutral-700">role-based access</strong>. Cancel anytime.
          </p>

          {/* See USD_PER_INR above — this converts the display, it isn't
              a second, separately-decided USD price point. */}
          <div className="mt-8 inline-flex items-center rounded-full border border-neutral-200 bg-neutral-50 p-1 text-sm">
            {['INR', 'USD'].map((c) => (
              <button
                key={c}
                onClick={() => setCurrency(c)}
                className={`rounded-full px-4 py-1.5 font-medium transition-colors ${
                  currency === c ? 'bg-neutral-900 text-white' : 'text-neutral-500 hover:text-neutral-900'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </motion.div>

        <div className="mt-10 grid gap-px overflow-hidden rounded-xl border border-neutral-200 bg-neutral-200 md:grid-cols-3">
          {PRICING_TIERS.map((tier, i) => (
            <motion.div
              key={tier.name}
              initial="hidden"
              animate="show"
              variants={fadeUp}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              className={`flex flex-col bg-white p-8 ${tier.highlighted ? 'relative bg-neutral-50' : ''}`}
            >
              {tier.highlighted && (
                <span className="absolute right-6 top-6 rounded-full bg-neutral-900 px-2.5 py-1 text-[11px] font-medium text-white">
                  Most popular
                </span>
              )}
              <p className="text-lg font-semibold text-neutral-900">{tier.name}</p>
              <p className="mt-1 text-sm text-neutral-500">{tier.tagline}</p>
              <p className="mt-6">
                <span className="text-4xl font-semibold tracking-tight text-neutral-900">
                  {formatPrice(tier.priceInr, currency)}
                </span>
                {tier.period && tier.priceInr !== null && (
                  <span className="ml-1 text-sm text-neutral-400">{tier.period}</span>
                )}
              </p>
              <button
                onClick={onGetStarted}
                className={`mt-6 rounded-md px-4 py-2.5 text-sm font-medium ${
                  tier.highlighted
                    ? 'bg-neutral-900 text-white hover:bg-neutral-700'
                    : 'border border-neutral-300 text-neutral-900 hover:bg-neutral-50'
                }`}
              >
                {tier.ctaLabel}
              </button>
              <ul className="mt-8 space-y-3 text-sm text-neutral-600">
                {tier.highlights.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mt-16 flex flex-col items-start justify-between gap-4 rounded-xl bg-neutral-900 px-8 py-8 text-white md:flex-row md:items-center"
        >
          <p className="text-lg font-medium">Running several schools, or need something custom?</p>
          <button
            onClick={onGetStarted}
            className="rounded-md bg-white px-5 py-2.5 text-sm font-medium text-neutral-900 hover:bg-neutral-200"
          >
            Get in touch
          </button>
        </motion.div>
      </div>
    </div>
  )
}
