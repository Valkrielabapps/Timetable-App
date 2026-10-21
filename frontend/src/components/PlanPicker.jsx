import { motion } from 'framer-motion'

/**
 * The first step after "Get started free": choose a plan, then create an
 * account. Matches the landing page's look (black, white type).
 *
 *   Free     -> sign up, 14 free days on Free limits, countdown in the app
 *   Pro      -> sign up, name the school, then straight to checkout
 *               (Settings > Plan & billing; the payment needs a school)
 *   Business -> Contact page
 *
 * The numbers mirror backend app/services/plans.py, which is what the app
 * actually enforces.
 */
// Same wording as the Pricing page (PricingPage.jsx's PRICING_TIERS), so a
// school sees one description of each plan wherever it looks.
const PLANS = [
  {
    id: 'free',
    name: 'Free',
    price: '₹0',
    period: 'for 14 days',
    blurb: 'Free for 14 days, no card needed',
    features: ['Up to 5 sections', '1 admin', '10 AI actions a month', 'Unlimited timetables', 'Exports carry "Made with Timetablz"'],
    cta: 'Start free',
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '₹4,999',
    period: '/year',
    blurb: 'For a school that needs more room to grow',
    features: ['Up to 60 sections', 'Up to 5 people with access', 'Unlimited AI setup, rules and edits', 'Clean PDF and Excel exports', 'Priority support'],
    cta: 'Choose Pro',
    highlighted: true,
  },
  {
    id: 'business',
    name: 'Business',
    price: 'Custom',
    period: '',
    blurb: 'For a group running several schools',
    features: ['Everything in Pro, plus:', 'Unlimited sections and people', 'Several schools in one account', 'Dedicated onboarding', 'Custom terms'],
    cta: 'Get in touch',
  },
]

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

// Styled exactly like the Pricing page's cards (PricingCard in
// PricingPage.jsx): dark cards, Pro outlined in white, the button above the
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
          <span className="rounded-full bg-neutral-900 px-2.5 py-0.5 text-[11px] font-medium text-white">Most chosen</span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-600">{plan.blurb}</p>

      <p className="mt-6">
        <span className="text-3xl font-semibold tracking-tight text-neutral-900">{plan.price}</span>
        {plan.period && <span className="ml-1 text-sm text-neutral-500">{plan.period}</span>}
      </p>

      <button
        onClick={() => onChoose(plan.id)}
        className={`mt-6 rounded-md px-5 py-2.5 text-sm font-medium ${
          plan.highlighted ? 'bg-neutral-900 text-white hover:bg-neutral-700' : 'border border-neutral-300 text-neutral-900 hover:bg-neutral-50'
        }`}
      >
        {plan.cta}
      </button>

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
            Start free for 14 days, no card needed. Upgrade to Pro whenever you&rsquo;re ready.
          </p>
        </motion.div>

        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {PLANS.map((plan, i) => (
            <PlanCard key={plan.id} plan={plan} onChoose={onChoose} delay={i * 0.08} />
          ))}
        </div>

        <p className="mt-8 text-sm text-neutral-500">
          After 14 days, a Free school is paused until it upgrades. Nothing you&rsquo;ve set up is deleted.
        </p>
      </div>
    </div>
  )
}
