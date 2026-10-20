import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import SiteNav from './SiteNav'
import SiteFooter from './SiteFooter'

/**
 * Standalone pricing page — reached via `?page=pricing` (see App.jsx,
 * same no-router pattern as AboutPage/SupportPage).
 *
 * Dark theme (bg-white, white text) matching About/Support/Customers/Why
 * Timetablz, by explicit request. Back to a three-card grid (Free / Pro /
 * Business side by side, Pro highlighted) rather than the single-column
 * row layout this page used before — also by explicit request, reverting
 * an earlier "de-templatify" pass that had swapped the card grid for
 * rows. Three tiers is a real, deliberate business decision (Free / Pro /
 * Business), not filler; the card grid is just how that decision reads
 * best now.
 *
 * Still left out, same reasoning as before:
 *   - The top logo strip / "70,000+ companies" trust line — no comparable
 *     customer count exists (see the Hero trust bar on the homepage).
 *   - The Monthly/Annual billing toggle — annual pricing hasn't been
 *     decided.
 *   - The "View Github / self-hosted" half of the closing banner — no
 *     public repo or self-hosted offering exists.
 *
 * The USD/INR toggle stays — see USD_PER_INR below on what it does and
 * doesn't represent.
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
    period: 'for 14 days',
    tagline: 'Free for 14 days, no card needed',
    highlights: ['Up to 5 sections', '1 admin', '10 AI actions a month', 'Unlimited timetables', 'Exports carry "Made with Timetablz"'],
    highlighted: false,
    ctaLabel: 'Get started free',
  },
  {
    name: 'Pro',
    priceInr: 4999,
    period: '/year',
    tagline: 'For a school that needs more room to grow',
    highlights: ['Up to 60 sections', 'Up to 5 people with access', 'Unlimited AI setup, rules and edits', 'Clean PDF and Excel exports', 'Priority support'],
    highlighted: true,
    ctaLabel: 'Get started',
  },
  {
    name: 'Business',
    priceInr: null,
    tagline: 'For a group running several schools',
    highlights: ['Everything in Pro, plus:', 'Unlimited sections and people', 'Several schools in one account', 'Dedicated onboarding', 'Custom terms'],
    highlighted: false,
    ctaLabel: 'Get in touch',
  },
]

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

// Billing-specific subset of the same honest-FAQ approach SupportPage.jsx
// uses — every answer here matches what docs/legal/TERMS_OF_SERVICE.md
// actually says (Section 6 pricing, Section 7 payment, Section 8
// refunds), not invented policy. The refund-window language stays vague
// on purpose since the real refund policy is still an open placeholder
// in that document (see [FREE TRIAL / PILOT PERIOD] and Section 8) —
// update this once that's decided.
const BILLING_FAQS = [
  {
    q: 'Does the price include GST?',
    a: 'The price shown is what you pay, in Indian Rupees. If GST becomes applicable to us, it will be shown separately at checkout and on your invoice.',
  },
  {
    q: 'Can I switch plans later?',
    a: "Yes. You can move from Free to Pro (or request a Business plan) at any point as your school's needs grow. You're not locked into whatever you pick today.",
  },
  {
    q: 'How does billing actually work?',
    a: 'Pro is paid in advance for one year at a time through Cashfree, our payment processor, and it does not renew automatically. If you cancel during the year, we refund the unused full months (see our Refund and Cancellation Policy).',
  },
  {
    q: 'What happens when my year of Pro ends?',
    a: "Nothing is deleted. For 15 days after the end date everything keeps working while you renew. After that the school is paused until you renew, and everything comes back exactly as you left it.",
  },
  {
    q: 'How does the free plan work?',
    a: 'Every new school gets 14 days free on the Free plan: up to 5 sections, one admin and 10 AI actions a month, no card needed. After 14 days the school is paused until it upgrades to Pro. Nothing you set up is deleted.',
  },
  {
    q: 'What happens if I cancel?',
    a: "Your school's data isn't deleted immediately. You keep access through the end of the period you've already paid for, and can export your timetables at any point before or after.",
  },
]

function BillingFaqItem({ item, isOpen, onToggle }) {
  return (
    <div className="border-b border-neutral-200">
      <button onClick={onToggle} className="flex w-full items-center justify-between gap-4 py-5 text-left">
        <span className="text-[15px] font-medium text-neutral-900">{item.q}</span>
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`shrink-0 text-neutral-500 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <p className="pb-5 pr-8 text-sm leading-relaxed text-neutral-600">{item.a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function formatPrice(priceInr, currency) {
  if (priceInr === null) return 'Custom'
  if (priceInr === 0) return currency === 'USD' ? '$0' : '₹0'
  if (currency === 'USD') {
    return `$${Math.round(priceInr * USD_PER_INR)}`
  }
  return `₹${priceInr.toLocaleString('en-IN')}`
}

function PricingCard({ tier, currency, onGetStarted, delay }) {
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={fadeUp}
      transition={{ duration: 0.4, delay }}
      className={`flex flex-col rounded-2xl p-8 ${
        tier.highlighted ? 'border-2 border-neutral-900 bg-neutral-50' : 'border border-neutral-200'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <p className="text-lg font-semibold text-neutral-900">{tier.name}</p>
        {tier.highlighted && (
          <span className="rounded-full bg-neutral-900 px-2.5 py-0.5 text-[11px] font-medium text-white">Most chosen</span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-600">{tier.tagline}</p>

      <p className="mt-6">
        <span className="text-3xl font-semibold tracking-tight text-neutral-900">{formatPrice(tier.priceInr, currency)}</span>
        {tier.period && tier.priceInr !== null && <span className="ml-1 text-sm text-neutral-500">{tier.period}</span>}
      </p>

      <button
        onClick={onGetStarted}
        className={`mt-6 rounded-md px-5 py-2.5 text-sm font-medium ${
          tier.highlighted ? 'bg-neutral-900 text-white hover:bg-neutral-700' : 'border border-neutral-300 text-neutral-900 hover:bg-neutral-50'
        }`}
      >
        {tier.ctaLabel}
      </button>

      <ul className="mt-8 space-y-3 border-t border-neutral-200 pt-6">
        {tier.highlights.map((h) => (
          <li key={h} className="flex items-start gap-2.5 text-sm text-neutral-700">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0 text-neutral-500">
              <path d="M20 6 9 17l-5-5" />
            </svg>
            {h}
          </li>
        ))}
      </ul>
    </motion.div>
  )
}

export default function PricingPage({ onBack, onGetStarted }) {
  const [currency, setCurrency] = useState('INR')
  const [openFaq, setOpenFaq] = useState(0)

  return (
    <div className="min-h-screen bg-white text-neutral-900">
      <SiteNav current="pricing" />

      <div className="mx-auto max-w-6xl px-6 py-16">
        <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.5 }}>
          <h1 className="font-serif text-4xl font-medium tracking-tight text-neutral-900 md:text-5xl">
            Find the plan that works for your school
          </h1>
          <p className="mt-4 max-w-xl text-neutral-600">
            Every plan includes <strong className="text-neutral-800">unlimited timetables</strong>,{' '}
            <strong className="text-neutral-800">conflict-free generation</strong>, and{' '}
            <strong className="text-neutral-800">role-based access</strong>. Cancel anytime.
          </p>

          {/* See USD_PER_INR above — this converts the display, it isn't
              a second, separately-decided USD price point. */}
          <div className="mt-8 inline-flex items-center rounded-full border border-neutral-200 bg-neutral-50 p-1 text-sm">
            {['INR', 'USD'].map((c) => (
              <button
                key={c}
                onClick={() => setCurrency(c)}
                className={`rounded-full px-4 py-1.5 font-medium transition-colors ${
                  currency === c ? 'bg-neutral-900 text-white' : 'text-neutral-600 hover:text-neutral-900'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </motion.div>

        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {PRICING_TIERS.map((tier, i) => (
            <PricingCard key={tier.name} tier={tier} currency={currency} onGetStarted={onGetStarted} delay={i * 0.08} />
          ))}
        </div>

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mx-auto mt-20 max-w-xl"
        >
          <h2 className="text-xl font-semibold tracking-tight text-neutral-900">Billing questions</h2>
          <div className="mt-4">
            {BILLING_FAQS.map((item, i) => (
              <BillingFaqItem
                key={item.q}
                item={item}
                isOpen={openFaq === i}
                onToggle={() => setOpenFaq(openFaq === i ? -1 : i)}
              />
            ))}
          </div>
        </motion.div>

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mt-16 flex flex-col items-start justify-between gap-4 rounded-xl border border-neutral-200 px-8 py-8 md:flex-row md:items-center"
        >
          <p className="text-lg font-medium text-neutral-900">Running several schools, or need something custom?</p>
          <button
            onClick={onGetStarted}
            className="rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700"
          >
            Get in touch
          </button>
        </motion.div>
      </div>
      <SiteFooter />
    </div>
  )
}
