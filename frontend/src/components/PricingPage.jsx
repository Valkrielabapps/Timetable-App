import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import SiteNav from './SiteNav'
import SiteFooter from './SiteFooter'
import {
  DONE_FOR_YOU, EVERY_PLAN, INVOICE_EMAIL, LARGE, PLANS, detectCurrency, largeBase, largePerSection, planPrice, saveCurrency,
} from '../lib/plans'

/**
 * Standalone pricing page - reached via `?page=pricing` (see App.jsx,
 * same no-router pattern as AboutPage/SupportPage).
 *
 * Dark theme (bg-white, white text) matching About/Support/Customers/Why
 * Timetablz, by explicit request. Four plans priced by the number of
 * sections (Starter / Standard / Plus / Large), each with a software price
 * and a "done for you" price; the numbers live in src/lib/plans.js.
 *
 * Still left out, same reasoning as before:
 *   - The top logo strip / "70,000+ companies" trust line - no comparable
 *     customer count exists (see the Hero trust bar on the homepage).
 *   - The Monthly/Annual billing toggle - annual pricing hasn't been
 *     decided.
 *   - The "View Github / self-hosted" half of the closing banner - no
 *     public repo or self-hosted offering exists.
 *
 * Currency: rupees for visitors in India, US dollars elsewhere (detected
 * from the browser's time zone, see detectCurrency in src/lib/plans.js);
 * the INR/USD switch changes it. The dollar prices are their own price
 * points (about 35% above the rupee ones), invoiced by email for now
 * because checkout is rupees only.
 */

function pricingTiers(currency) {
  return [
    ...PLANS.map((p) => ({
      name: p.name,
      price: planPrice(p, currency),
      period: '/year',
      doneForYou: planPrice(p, currency, 'done_for_you'),
      tagline: p.sections,
      highlights: EVERY_PLAN,
      highlighted: p.id === 'standard',
      ctaLabel: 'Start free trial',
    })),
    {
      name: LARGE.name,
      price: largeBase(currency),
      period: '/year',
      pricePrefix: 'From ',
      priceNote: `+ ${largePerSection(currency)} a year for each section above ${LARGE.from}`,
      doneForYouText: 'Done for you: quoted',
      tagline: LARGE.sections,
      highlights: [...EVERY_PLAN, 'Several schools in one account'],
      highlighted: false,
      ctaLabel: 'Get in touch',
      href: '/contact',
    },
  ]
}

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

// Billing-specific subset of the same honest-FAQ approach SupportPage.jsx
// uses - every answer here matches what docs/legal/TERMS_OF_SERVICE.md
// actually says (Section 6 pricing, Section 7 payment, Section 8
// refunds), not invented policy. The refund-window language stays vague
// on purpose since the real refund policy is still an open placeholder
// in that document (see [FREE TRIAL / PILOT PERIOD] and Section 8) - 
// update this once that's decided.
export const BILLING_FAQS = [
  {
    q: 'How do I pick a plan?',
    a: `By the number of sections in your school (each class division, like 6A or 6B, is a section). Starter is up to 30, Standard 31 to 50, Plus 51 to 80. Over 80, or several schools in a group, the ${LARGE.name} plan is ₹${LARGE.base.toLocaleString('en-IN')} plus ₹${LARGE.perSection} a year for each section above ${LARGE.from}. Every plan has every feature.`,
  },
  {
    q: 'What is “Done for you”?',
    a: `${DONE_FOR_YOU} You send us your staff and allotment sheets; we do the rest and hand you a working timetable.`,
  },
  {
    q: 'Does the price include GST?',
    a: 'The price shown is what you pay, in Indian Rupees. If GST becomes applicable to us, it will be shown separately at checkout and on your invoice.',
  },
  {
    q: 'How does the free trial work?',
    a: 'Every new school gets 14 days with everything unlocked, no card needed. After 14 days the school is paused until you choose a plan. Nothing you set up is deleted.',
  },
  {
    q: 'How does billing work?',
    a: 'Plans are paid in advance for one year at a time through Cashfree, our payment processor, and do not renew automatically. If you cancel during the year, we refund the unused full months (see our Refund and Cancellation Policy).',
  },
  {
    q: 'Can I change plans later?',
    a: 'Yes. If your school grows past your plan’s sections, move up to the next plan at any time from Settings > Plan & billing.',
  },
  {
    q: 'What happens when my year ends?',
    a: 'Nothing is deleted. For 15 days after the end date everything keeps working while you renew. After that the school is paused until you renew, and everything comes back exactly as you left it.',
  },
]

/** The FAQs as a visitor paying in dollars should read them. */
export function billingFaqs(currency) {
  if (currency !== 'USD') return BILLING_FAQS
  const [, ...rest] = BILLING_FAQS
  const pick = {
    q: 'How do I pick a plan?',
    a: `By the number of sections in your school (each class division, like 6A or 6B, is a section). Starter is up to 30, Standard 31 to 50, Plus 51 to 80. Over 80, or several schools in a group, the ${LARGE.name} plan is ${largeBase('USD')} plus ${largePerSection('USD')} a year for each section above ${LARGE.from}. Every plan has every feature.`,
  }
  const abroad = {
    q: 'We’re outside India. How do we pay?',
    a: `Prices outside India are in US dollars. Start the free trial as usual; when you’re ready to buy, choose your plan in Settings > Plan & billing and we’ll email you an invoice, or write to ${INVOICE_EMAIL}. Any local taxes or bank charges on your side are yours.`,
  }
  return [
    pick,
    abroad,
    ...rest.map((f) =>
      f.q === 'Does the price include GST?'
        ? { q: 'Does the price include tax?', a: 'The price shown is what we invoice, in US dollars. Indian GST does not apply to schools outside India.' }
        : f.q === 'How does billing work?'
          ? { ...f, a: 'Plans are paid in advance for one year at a time, by invoice, and do not renew automatically. If you cancel during the year, we refund the unused full months (see our Refund and Cancellation Policy).' }
          : f,
    ),
  ]
}

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

function PricingCard({ tier, onGetStarted, delay }) {
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
          <span className="rounded-full bg-neutral-900 px-2.5 py-0.5 text-[11px] font-medium text-white">Mid-size schools</span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-600">{tier.tagline}</p>

      <p className="mt-6">
        {tier.pricePrefix && <span className="text-sm text-neutral-500">{tier.pricePrefix}</span>}
        <span className="text-3xl font-semibold tracking-tight text-neutral-900">{tier.price}</span>
        {tier.period && <span className="ml-1 text-sm text-neutral-500">{tier.period}</span>}
      </p>
      {tier.priceNote && <p className="mt-1 text-xs text-neutral-500">{tier.priceNote}</p>}
      <p className="mt-2 rounded-md bg-neutral-100 px-3 py-2 text-sm text-neutral-700">
        {tier.doneForYou
          ? <>Done for you: <strong>{tier.doneForYou}</strong> <span className="text-neutral-500">first year, setup included</span></>
          : tier.doneForYouText}
      </p>

      <button
        onClick={() => (tier.href ? window.location.assign(tier.href) : onGetStarted())}
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
  const [currency, setCurrencyState] = useState(detectCurrency)
  const [openFaq, setOpenFaq] = useState(0)
  const tiers = pricingTiers(currency)
  const faqs = billingFaqs(currency)
  function setCurrency(c) {
    setCurrencyState(c)
    saveCurrency(c)
  }

  return (
    <div className="min-h-screen bg-white text-neutral-900">
      <SiteNav current="pricing" />

      <div className="mx-auto max-w-6xl px-6 py-16">
        <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.5 }}>
          <h1 className="font-serif text-4xl font-medium tracking-tight text-neutral-900 md:text-5xl">
            Find the plan that works for your school
          </h1>
          <p className="mt-4 max-w-2xl text-neutral-600">
            Priced by the number of sections in your school. Every plan has{' '}
            <strong className="text-neutral-800">every feature</strong>,{' '}
            <strong className="text-neutral-800">unlimited people and AI</strong>, and clean exports. Choose{' '}
            <strong className="text-neutral-800">Done for you</strong> and we set it all up.
          </p>
          <p className="mt-2 text-sm text-neutral-500">Start with a 14-day free trial, everything unlocked, no card needed. Prices are per year.</p>

          {/* Rupees in India, dollars elsewhere; both are real price points. */}
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
          {currency === 'USD' && (
            <p className="mt-3 text-sm text-neutral-500">Prices for schools outside India, in US dollars. We invoice you by email.</p>
          )}
        </motion.div>

        <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {tiers.map((tier, i) => (
            <PricingCard key={tier.name} tier={tier} onGetStarted={onGetStarted} delay={i * 0.08} />
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
            {faqs.map((item, i) => (
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
          <p className="text-lg font-medium text-neutral-900">More than 80 sections, or running several schools?</p>
          <button
            onClick={() => window.location.assign('/contact')}
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
