import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

/**
 * Standalone pricing page — reached via `?page=pricing` (see App.jsx,
 * same no-router pattern as AboutPage/SupportPage).
 *
 * Dark theme (bg-black, white text) matching About/Support/Customers/Why
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
    a: 'No — prices shown are exclusive of applicable taxes. GST is added at checkout or on your invoice, same as the Terms of Service state.',
  },
  {
    q: 'Can I switch plans later?',
    a: "Yes. You can move from Free to Pro (or request a Business plan) at any point as your school's needs grow — you're not locked into whatever you pick today.",
  },
  {
    q: 'How does billing actually work?',
    a: 'Pro is billed in advance on a recurring monthly basis through Razorpay, our payment processor. You can cancel any time from your account settings; cancellation takes effect at the end of your current billing period, and you keep access until then.',
  },
  {
    q: 'What happens if I cancel?',
    a: "Your school's data isn't deleted immediately — you keep access through the end of the period you've already paid for, and can export your timetables at any point before or after.",
  },
]

function BillingFaqItem({ item, isOpen, onToggle }) {
  return (
    <div className="border-b border-white/10">
      <button onClick={onToggle} className="flex w-full items-center justify-between gap-4 py-5 text-left">
        <span className="text-[15px] font-medium text-white">{item.q}</span>
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
            <p className="pb-5 pr-8 text-sm leading-relaxed text-neutral-400">{item.a}</p>
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
        tier.highlighted ? 'border-2 border-white bg-white/5' : 'border border-white/10'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <p className="text-lg font-semibold text-white">{tier.name}</p>
        {tier.highlighted && (
          <span className="rounded-full bg-white px-2.5 py-0.5 text-[11px] font-medium text-black">Most chosen</span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-400">{tier.tagline}</p>

      <p className="mt-6">
        <span className="text-3xl font-semibold tracking-tight text-white">{formatPrice(tier.priceInr, currency)}</span>
        {tier.period && tier.priceInr !== null && <span className="ml-1 text-sm text-neutral-500">{tier.period}</span>}
      </p>

      <button
        onClick={onGetStarted}
        className={`mt-6 rounded-md px-5 py-2.5 text-sm font-medium ${
          tier.highlighted ? 'bg-white text-black hover:bg-neutral-200' : 'border border-white/20 text-white hover:bg-white/5'
        }`}
      >
        {tier.ctaLabel}
      </button>

      <ul className="mt-8 space-y-3 border-t border-white/10 pt-6">
        {tier.highlights.map((h) => (
          <li key={h} className="flex items-start gap-2.5 text-sm text-neutral-300">
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
    <div className="min-h-screen bg-black text-white">
      <div className="sticky top-0 z-30 border-b border-white/10 bg-black">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <button onClick={onBack} className="text-[17px] font-bold tracking-tight text-white">
            Timetablz
          </button>
          <div className="flex items-center gap-5">
            <button onClick={onBack} className="text-sm font-medium text-neutral-400 hover:text-white">
              ← Back to home
            </button>
            <button
              onClick={onGetStarted}
              className="rounded-md bg-white px-4 py-2 text-sm font-medium text-black hover:bg-neutral-200"
            >
              Get started free
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-16">
        <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.5 }}>
          <h1 className="font-serif text-4xl font-medium tracking-tight text-white md:text-5xl">
            Find the plan that works for your school
          </h1>
          <p className="mt-4 max-w-xl text-neutral-400">
            Every plan includes <strong className="text-neutral-200">unlimited timetables</strong>,{' '}
            <strong className="text-neutral-200">conflict-free generation</strong>, and{' '}
            <strong className="text-neutral-200">role-based access</strong>. Cancel anytime.
          </p>

          {/* See USD_PER_INR above — this converts the display, it isn't
              a second, separately-decided USD price point. */}
          <div className="mt-8 inline-flex items-center rounded-full border border-white/15 bg-white/5 p-1 text-sm">
            {['INR', 'USD'].map((c) => (
              <button
                key={c}
                onClick={() => setCurrency(c)}
                className={`rounded-full px-4 py-1.5 font-medium transition-colors ${
                  currency === c ? 'bg-white text-black' : 'text-neutral-400 hover:text-white'
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
          <h2 className="text-xl font-semibold tracking-tight text-white">Billing questions</h2>
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
          className="mt-16 flex flex-col items-start justify-between gap-4 rounded-xl border border-white/10 px-8 py-8 md:flex-row md:items-center"
        >
          <p className="text-lg font-medium text-white">Running several schools, or need something custom?</p>
          <button
            onClick={onGetStarted}
            className="rounded-md bg-white px-5 py-2.5 text-sm font-medium text-black hover:bg-neutral-200"
          >
            Get in touch
          </button>
        </motion.div>
      </div>
    </div>
  )
}
