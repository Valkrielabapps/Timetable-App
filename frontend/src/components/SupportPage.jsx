import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import SiteNav from './SiteNav'
import SiteFooter from './SiteFooter'

/**
 * Standalone Support page - contact details and FAQ - reached via
 * `?page=support` (same no-router pattern as PricingPage/AboutPage; see
 * App.jsx). Every answer describes something the product does today; keep
 * it that way when editing. Plan numbers mirror app/services/plans.py and
 * the refund wording mirrors src/legal/refund-policy.md.
 *
 * Dark theme and wide two-column rows, matching AboutPage.jsx.
 */

const SUPPORT_EMAIL = 'support@timetablz.com'

export const FAQ_GROUPS = [
  {
    title: 'Getting started',
    items: [
      {
        q: 'How do I set up my school?',
        a: 'Follow the five steps along the top of the app: Setup (your days, periods and breaks), Subjects, Teachers, Constraints, then Timetable. Each section gets its own weekly plan of subjects and periods, and "Copy to other sections" fills in the rest of a grade in one go.',
      },
      {
        q: 'Can I import my existing spreadsheet instead of typing everything in?',
        a: "Yes. Bulk import accepts a CSV or Excel file for subjects, teachers and rooms. There's also an AI-assisted option that reads an existing staff list or old timetable and proposes the records for you to review before anything is created.",
      },
      {
        q: 'Can more than one person work on the same school?',
        a: 'Yes, on the Pro plan (up to 5 people). Invite colleagues by email as an admin, who can edit everything, or a viewer, who can only look. You can see who has access from Settings at any time.',
      },
    ],
  },
  {
    title: 'Timetables',
    items: [
      {
        q: 'How long does generating a timetable take?',
        a: 'Usually a few seconds, and under a minute even for large schools. It runs in the background, so you can keep working in another tab while it does.',
      },
      {
        q: "What happens if a timetable can't be generated?",
        a: "Some combinations of rules can't all be met at once - for example, a subject needing 8 periods a week when your rules only leave room for 5. Instead of producing a broken timetable, Timetablz shows a popup listing each reason in plain language, so you know exactly which rule or teacher to change.",
      },
      {
        q: 'Can I adjust a generated timetable by hand?',
        a: 'Yes. Drag a slot to another cell (refused automatically if it would double-book a teacher or room), or click it to lock it in place so it stays put the next time you regenerate. You can also type an edit in plain English, like "move Math to period 2 on Wednesday".',
      },
      {
        q: 'Does it handle electives and lab batches?',
        a: 'Yes. Elective blocks run several subjects in the same period, with each student taking one, and you can export the timetable each combination of choices actually gets. Lab subjects can be split into batches, each with its own teacher and room.',
      },
      {
        q: 'What if a teacher is unexpectedly absent?',
        a: "The Substitutions view, inside the Timetable tab, suggests a qualified, free teacher for each of the absent teacher's periods, instead of you scanning the whole staff list.",
      },
      {
        q: 'Can I export the finished timetable?',
        a: 'Yes, as Excel or PDF: one page per section in grade order, followed by one per teacher, ready to print or send. On Pro you can leave off the Timetablz watermark.',
      },
    ],
  },
  {
    title: 'Plans and billing',
    items: [
      {
        q: 'Is there a free plan?',
        a: 'Every new school gets a 14-day free period on the Free plan: up to 5 sections, one admin and 10 AI actions a month. After 14 days the school is locked until you upgrade - your data is kept and comes back the moment you do.',
      },
      {
        q: "What's included in Pro?",
        a: 'Pro is ₹4,999 a year: up to 60 sections, 5 people, unlimited AI actions and exports without the watermark. Larger schools and groups can ask us for a Business plan priced to their size.',
      },
      {
        q: 'How do I pay, and do I get an invoice?',
        a: 'Go to Settings > Plan & billing and click Pay now. Payment is through Cashfree Payments (UPI, cards or net banking). An invoice is issued for every payment and can be downloaded from the same page.',
      },
      {
        q: 'Does Pro renew automatically?',
        a: "No, nothing is charged automatically. When your year is up you get a 15-day grace period with everything still working, so there's time to renew.",
      },
      {
        q: 'Can I cancel or get a refund?',
        a: `Yes. Email ${SUPPORT_EMAIL} from a school admin's address and we refund the unused full months of your year. Duplicate or failed payments are refunded in full. See the Refund and Cancellation Policy for the details.`,
      },
    ],
  },
  {
    title: 'Data and privacy',
    items: [
      {
        q: 'Does the AI ever see student data?',
        a: 'No. Timetablz never needs individual student records: a section is just a name and a grade, so there is nothing about students for the AI features to read.',
      },
      {
        q: 'What happens to my data if I stop using Timetablz?',
        a: 'It stays in your account - moving to the Free plan or letting the free period end never deletes anything. If you want it deleted, email us and we will remove it.',
      },
    ],
  },
]

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

function FaqItem({ item, isOpen, onToggle }) {
  return (
    <div className="border-b border-neutral-200">
      <button onClick={onToggle} aria-expanded={isOpen} className="flex w-full items-center justify-between gap-4 py-5 text-left">
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
          aria-hidden="true"
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

function ContactCard({ title, children, action }) {
  return (
    <div className="flex flex-col justify-between gap-5 rounded-xl border border-neutral-200 bg-neutral-50 p-6">
      <div>
        <h3 className="text-[15px] font-semibold text-neutral-900">{title}</h3>
        <div className="mt-2 text-sm leading-relaxed text-neutral-600">{children}</div>
      </div>
      {action}
    </div>
  )
}

function Row({ heading, children, amount = 0.2 }) {
  return (
    <motion.div
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount }}
      variants={fadeUp}
      transition={{ duration: 0.5 }}
      className="grid gap-6 py-14 md:grid-cols-[280px_1fr] md:gap-12"
    >
      <h2 className="font-serif text-3xl font-medium text-neutral-900">{heading}</h2>
      <div className="min-w-0">{children}</div>
    </motion.div>
  )
}

export default function SupportPage({ onBack, onGetStarted }) {
  // Keyed "group:index" so one answer is open across the whole page.
  const [open, setOpen] = useState('0:0')
  const [copied, setCopied] = useState(false)

  async function copyEmail() {
    try {
      await navigator.clipboard.writeText(SUPPORT_EMAIL)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      // Clipboard blocked: the address is on screen to copy by hand.
    }
  }

  return (
    <div className="min-h-screen bg-white text-neutral-900">
      <SiteNav current="support" />

      <div className="mx-auto max-w-6xl px-6 py-20">
        <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.5 }}>
          <h1 className="font-serif text-5xl font-medium leading-tight tracking-tight text-neutral-900 md:text-6xl">
            Support
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-neutral-600">
            We&rsquo;re a small team and read every message. Most get a reply within one working day.
          </p>
        </motion.div>

        <div className="mt-20 divide-y divide-neutral-200 border-t border-neutral-200">
          <Row heading="Contact us" amount={0.3}>
            <div className="grid gap-4 sm:grid-cols-2">
              <ContactCard
                title="Email"
                action={
                  <div className="flex flex-wrap items-center gap-3">
                    <a
                      href={`mailto:${SUPPORT_EMAIL}`}
                      className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
                    >
                      {SUPPORT_EMAIL}
                    </a>
                    <button onClick={copyEmail} className="text-sm font-medium text-neutral-600 hover:text-neutral-900">
                      {copied ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                }
              >
                Questions, problems with a timetable, billing and refunds, or a demo for your school.
              </ContactCard>
              <ContactCard
                title="From inside the app"
                action={<span className="text-sm font-medium text-neutral-700">Help button, bottom right</span>}
              >
                Signed in? Use the Help button on any screen to send us a ticket. It includes your school, so
                we can look into it straight away.
              </ContactCard>
              <ContactCard
                title="Payments and refunds"
                action={
                  <a href="/refunds" className="text-sm font-medium text-neutral-900 underline underline-offset-4 hover:text-neutral-600">
                    Refund and Cancellation Policy
                  </a>
                }
              >
                Charged twice, or paid but still on Free? Email us the order reference from the payment page and
                we&rsquo;ll fix it within 3 working days.
              </ContactCard>
              <ContactCard
                title="Larger schools"
                action={
                  <a href="/pricing" className="text-sm font-medium text-neutral-900 underline underline-offset-4 hover:text-neutral-600">
                    See plans
                  </a>
                }
              >
                More than 60 sections, or several schools in a group? Write to us for a Business plan priced to
                your size.
              </ContactCard>
            </div>
          </Row>

          <Row
            heading={
              <>
                Frequently asked
                <br />
                questions
              </>
            }
          >
            <div className="flex flex-col gap-12">
              {FAQ_GROUPS.map((group, g) => (
                <div key={group.title}>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">{group.title}</h3>
                  {group.items.map((item, i) => {
                    const id = `${g}:${i}`
                    return (
                      <FaqItem
                        key={item.q}
                        item={item}
                        isOpen={open === id}
                        onToggle={() => setOpen(open === id ? null : id)}
                      />
                    )
                  })}
                </div>
              ))}
            </div>
          </Row>
        </div>

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mt-16 flex flex-col items-start justify-between gap-4 rounded-xl border border-neutral-200 px-8 py-8 md:flex-row md:items-center"
        >
          <div>
            <p className="text-lg font-medium text-neutral-900">Didn&rsquo;t find your answer?</p>
            <p className="mt-1 text-sm text-neutral-600">Write to us and a real person will reply.</p>
          </div>
          <a
            href={`mailto:${SUPPORT_EMAIL}`}
            className="rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700"
          >
            Email support
          </a>
        </motion.div>
      </div>
      <SiteFooter />
    </div>
  )
}
