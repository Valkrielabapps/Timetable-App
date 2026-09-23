import { motion } from 'framer-motion'

/**
 * Standalone About/Company page — reached via `?page=about` (same
 * no-router pattern as PricingPage/SupportPage; see App.jsx). Dark theme
 * (black background, matching Hero/WhyTimetablzPage) per explicit
 * request, modeled loosely on the Griffin "Hello, we're Griffin" about
 * page structure the user referenced (short section headings, generous
 * spacing, no narrow centered column) — adapted to Timetablz's own
 * content rather than reusing Griffin's copy.
 *
 * Kept deliberately honest about where the company actually is right
 * now, same standard applied everywhere else on this site (see
 * MetricsSection's placeholder-metrics warning and TESTIMONIAL_TILE_
 * STYLES in LandingPage.jsx): no fabricated founding story, no invented
 * team bios or headshots, no "after years at [big company]" backstory
 * that was never stated, and — per explicit request — no founder name
 * mentioned anywhere on this page. What's here is limited to what's
 * actually known: the real problem the product solves, what's been
 * built, and the one real school partner (Shishya Public School,
 * Dehradun) — rather than padding it out with a polished-sounding
 * narrative that isn't true yet.
 */

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

const SECTIONS = [
  {
    heading: 'Who we are',
    body: [
      "Timetablz is a scheduling platform built for schools and colleges, not a generic project-planning tool with \"education\" bolted on. It exists because building a class timetable by hand takes days, sometimes weeks, and most of that work gets redone from scratch every single term.",
    ],
  },
  {
    heading: 'The problem',
    body: [
      'A timetable has to satisfy dozens of constraints at once: no teacher in two places, no room double-booked, subject-load limits, availability windows, and whatever else a particular school needs. Doing that by hand means holding all of it in your head or across several spreadsheets, and a single change (a new teacher, a room going out of service) can mean starting large parts of it over.',
      "That's real, recurring work for an admin every term, for something a computer is actually well-suited to handle.",
    ],
  },
  {
    heading: 'What we built',
    body: [
      "Timetablz takes a school's periods, subjects, teachers, rooms, and scheduling rules, and hands them to a constraint-solving engine that builds every section's timetable at once, with zero clashes. Rules can be typed as plain sentences instead of configured through menus.",
      "When a set of rules genuinely can't all be satisfied together, the product says so and explains which rule is the problem, instead of quietly producing something broken.",
    ],
  },
  {
    heading: 'Where we are today',
    body: [
      "Timetablz is early. Our first real school partner is Shishya Public School, Dehradun, and we're building alongside them rather than claiming a scale we haven't reached yet.",
      "If you've read this far, you've probably noticed this site doesn't lean on big customer counts or manufactured social proof. We'd rather be straightforward about being early than dress it up.",
    ],
  },
]

export default function AboutPage({ onBack, onGetStarted }) {
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
            Hello, we're Timetablz
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-neutral-400">
            We build scheduling software for schools and colleges that want a timetable done in an afternoon,
            not weeks.
          </p>
        </motion.div>

        {/* A wide two-column row per section — a short heading on the
            left, the body copy on the right — rather than one narrow
            centered column of text. Spreads the page across its full
            width the way the Griffin reference does, instead of
            cramming everything into a single skinny strip down the
            middle. */}
        <div className="mt-20 divide-y divide-white/10 border-t border-white/10">
          {SECTIONS.map((section, i) => (
            <motion.div
              key={section.heading}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, amount: 0.3 }}
              variants={fadeUp}
              transition={{ duration: 0.5, delay: i * 0.05 }}
              className="grid gap-4 py-14 md:grid-cols-[280px_1fr] md:gap-12"
            >
              <h2 className="font-serif text-3xl font-medium text-white">{section.heading}</h2>
              <div className="max-w-2xl space-y-4 text-[15px] leading-relaxed text-neutral-400">
                {section.body.map((para) => (
                  <p key={para.slice(0, 24)}>{para}</p>
                ))}
              </div>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mt-16 flex flex-col items-start justify-between gap-4 rounded-xl border border-white/10 px-8 py-8 md:flex-row md:items-center"
        >
          <p className="text-lg font-medium text-white">Want to see it on your school's own timetable?</p>
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
