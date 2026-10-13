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
const PLANS = [
  {
    id: 'free',
    name: 'Free',
    price: '₹0',
    period: 'for 14 days',
    blurb: 'Try Timetablz with a few sections.',
    features: ['Up to 5 sections', '1 admin', '10 AI actions a month', 'Unlimited timetables', 'PDF and Excel exports'],
    cta: 'Start free',
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '₹4,999',
    period: 'a year',
    blurb: 'For a whole school.',
    features: ['Up to 60 sections', 'Up to 5 people with access', 'Unlimited AI setup, rules and edits', 'Clean exports, no branding', 'Priority support'],
    cta: 'Choose Pro',
    highlighted: true,
  },
  {
    id: 'business',
    name: 'Business',
    price: 'Custom',
    period: '',
    blurb: 'For groups running several schools.',
    features: ['Everything in Pro', 'Unlimited sections and people', 'Several schools in one account', 'Dedicated onboarding'],
    cta: 'Contact us',
  },
]

export default function PlanPicker({ onChoose, onBack, onSignIn }) {
  return (
    <div className="min-h-screen bg-black text-white">
      <div className="flex items-center px-8 py-5 md:px-16 lg:px-28">
        <button onClick={onBack} className="text-[19px] font-bold tracking-tight">
          Timetablz
        </button>
        <div className="ml-auto flex items-center gap-6 text-[15px]">
          <button onClick={onSignIn} className="font-medium text-neutral-300 hover:text-white">
            Sign in
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 pb-20 pt-10">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="text-center">
          <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">Choose how you want to start</h1>
          <p className="mx-auto mt-4 max-w-xl text-neutral-400">
            Start free for 14 days, no card needed. Upgrade to Pro whenever you&rsquo;re ready.
          </p>
        </motion.div>

        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {PLANS.map((plan, i) => (
            <motion.div
              key={plan.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.05 * (i + 1) }}
              className={`flex flex-col rounded-2xl border p-7 ${
                plan.highlighted ? 'border-white bg-white text-black' : 'border-white/15 bg-white/[0.03]'
              }`}
            >
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{plan.name}</h2>
                {plan.highlighted && (
                  <span className="rounded-full bg-black px-2.5 py-0.5 text-xs font-medium text-white">Most schools</span>
                )}
              </div>
              <p className={`mt-1 text-sm ${plan.highlighted ? 'text-neutral-600' : 'text-neutral-400'}`}>{plan.blurb}</p>
              <p className="mt-6">
                <span className="text-4xl font-semibold tracking-tight">{plan.price}</span>
                {plan.period && (
                  <span className={`ml-1.5 text-sm ${plan.highlighted ? 'text-neutral-600' : 'text-neutral-400'}`}>{plan.period}</span>
                )}
              </p>
              <ul className={`mt-6 flex-1 space-y-2.5 text-sm ${plan.highlighted ? 'text-neutral-800' : 'text-neutral-300'}`}>
                {plan.features.map((f) => (
                  <li key={f} className="flex gap-2.5">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-none" aria-hidden="true">
                      <path d="M5 12.5l4.5 4.5L19 7.5" />
                    </svg>
                    {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => onChoose(plan.id)}
                className={`mt-8 rounded-lg px-4 py-3 text-sm font-semibold ${
                  plan.highlighted ? 'bg-black text-white hover:bg-neutral-800' : 'bg-white text-black hover:bg-neutral-200'
                }`}
              >
                {plan.cta}
              </button>
            </motion.div>
          ))}
        </div>

        <p className="mt-8 text-center text-sm text-neutral-500">
          After 14 days, a Free school is paused until it upgrades. Nothing you&rsquo;ve set up is deleted.
        </p>
      </div>
    </div>
  )
}
