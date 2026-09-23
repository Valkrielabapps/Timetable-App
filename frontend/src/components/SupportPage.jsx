import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

/**
 * Standalone Support page — contact info + FAQ — reached via
 * `?page=support` (same no-router pattern as PricingPage/AboutPage; see
 * App.jsx). Every FAQ answer below describes something the product
 * actually does today (see docs/ARCHITECTURE.md, docs/GETTING_STARTED.md,
 * and docs/legal/PRIVACY_POLICY.md), nothing invented, same standard
 * applied to PricingPage's feature list.
 *
 * Dark theme and wide two-column section layout, matching AboutPage.jsx
 * by explicit request ("adjust the support page accordingly") rather
 * than the narrower white-background layout this page used before.
 *
 * The contact email is a `[SUPPORT_EMAIL]` placeholder, not a real
 * address, same unresolved gap as the footer's dropped "Contact us" link
 * and the legal pages' unfilled placeholders (business email/domain
 * hasn't been decided yet). Still flagged with a warning-colored notice,
 * adapted to the dark theme, rather than a fake mailto that would
 * silently bounce.
 */

const FAQS = [
  {
    q: "What happens if a timetable can't be generated?",
    a: 'Some combinations of rules are mathematically impossible to satisfy at the same time. The solver detects this instead of producing a broken result, and explains in plain language which rule or teacher is the problem, so it takes minutes to fix rather than hours of trial and error.',
  },
  {
    q: 'Can I import my existing spreadsheet instead of typing everything in?',
    a: "Yes. Bulk import accepts a CSV or Excel file for subjects, teachers, and rooms. There's also an AI-assisted option that reads an existing staff list or old timetable file and proposes the records for you to review before they're created.",
  },
  {
    q: 'Does the AI ever see individual student data?',
    a: 'No. The product is deliberately built to avoid needing individual student records. A section only stores an aggregate count (e.g. "32 students in Grade 8 - A"), not names or IDs, so there\'s nothing student-identifying for the AI features to process.',
  },
  {
    q: 'How long does generating a timetable take?',
    a: 'Typically well under a minute. Generation runs as a background job, so the button shows "Generating…" while it works rather than holding your browser on a long request.',
  },
  {
    q: 'Can I adjust a generated timetable by hand?',
    a: 'Yes. Drag any slot to a different cell (rejected automatically if it would double-book a class, teacher, or room), or lock a slot in place so it stays exactly where it is the next time you regenerate.',
  },
  {
    q: 'What if a teacher is unexpectedly unavailable?',
    a: "The Substitutions view suggests a qualified, available replacement for that teacher's affected periods, instead of you scanning the whole staff list by hand.",
  },
  {
    q: 'Can more than one person work on the same school?',
    a: 'Yes. Invite colleagues by email as an admin (can edit everything) or a viewer (read-only). You can see exactly who has access from the Team tab at any time.',
  },
  {
    q: 'Can I export the finished timetable?',
    a: 'Yes. Export the whole school as Excel or PDF, one sheet or page per section followed by one per teacher, ready to print or email out.',
  },
]

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

function FaqItem({ item, isOpen, onToggle }) {
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

export default function SupportPage({ onBack, onGetStarted }) {
  const [openIndex, setOpenIndex] = useState(0)

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

      <div className="mx-auto max-w-6xl px-6 py-20">
        <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.5 }}>
          <h1 className="font-serif text-5xl font-medium leading-tight tracking-tight text-white md:text-6xl">
            Support
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-neutral-400">
            Reach us directly, or check the answers below first. Most questions are covered.
          </p>
        </motion.div>

        {/* Same wide two-column row pattern as AboutPage.jsx: a short
            heading on the left, content on the right, rather than one
            narrow centered column. */}
        <div className="mt-20 divide-y divide-white/10 border-t border-white/10">
          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.3 }}
            variants={fadeUp}
            transition={{ duration: 0.5 }}
            className="grid gap-4 py-14 md:grid-cols-[280px_1fr] md:gap-12"
          >
            <h2 className="font-serif text-3xl font-medium text-white">Contact us</h2>
            <div className="max-w-2xl">
              {/* See this file's top docstring. The address/domain isn't
                  decided yet. This notice stays until it is; don't
                  quietly replace it with a made-up address. */}
              <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">
                A direct support email is coming soon. The business email/domain hasn't been finalized yet.
                In the meantime, use <span className="font-medium">Get started</span> below to create an
                account, or reach out through whatever channel got you to this page.
              </div>
            </div>
          </motion.div>

          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
            variants={fadeUp}
            transition={{ duration: 0.5 }}
            className="grid gap-4 py-14 md:grid-cols-[280px_1fr] md:gap-12"
          >
            <h2 className="font-serif text-3xl font-medium text-white">
              Frequently asked
              <br />
              questions
            </h2>
            <div className="max-w-2xl">
              {FAQS.map((item, i) => (
                <FaqItem
                  key={item.q}
                  item={item}
                  isOpen={openIndex === i}
                  onToggle={() => setOpenIndex(openIndex === i ? -1 : i)}
                />
              ))}
            </div>
          </motion.div>
        </div>

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mt-16 flex flex-col items-start justify-between gap-4 rounded-xl border border-white/10 px-8 py-8 md:flex-row md:items-center"
        >
          <p className="text-lg font-medium text-white">Still stuck, or found something we missed?</p>
          <button
            onClick={onGetStarted}
            className="rounded-md bg-white px-5 py-2.5 text-sm font-medium text-black hover:bg-neutral-200"
          >
            Get started free
          </button>
        </motion.div>
      </div>
    </div>
  )
}
