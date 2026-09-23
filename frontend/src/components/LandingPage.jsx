import { AnimatePresence, motion } from 'framer-motion'
import { Fragment, useEffect, useState } from 'react'
import { Marquee } from './Marquee'
import shishyaPublicSchoolPhoto from '../assets/shishya-public-school.png'
import shishyaPublicSchoolGatePhoto from '../assets/shishya-public-school-gate.png'
import shishyaPublicSchoolEntrancePhoto from '../assets/shishya-public-school-entrance.png'

/**
 * Marketing landing page — what an unauthenticated visitor sees before
 * AuthPage.jsx, instead of landing straight on a login form. App.jsx
 * renders this first and only swaps to AuthPage once `onGetStarted` is
 * called (a "Get started" / "Sign in" click), so bookmarking straight
 * into login isn't supported yet — not a real gap for a single-page app
 * with no router, just worth knowing if that's ever needed later.
 *
 * Content notes for whoever edits this next:
 *   - PRICING is explicitly placeholder (see the section below) — actual
 *     pricing hasn't been decided yet (see docs/ARCHITECTURE.md and the
 *     business-side conversation this was built alongside). Replace the
 *     numbers before this goes live for real, or swap the section for a
 *     "Contact us" CTA if usage-based/custom pricing ends up being the
 *     model instead.
 *   - TESTIMONIALS are placeholder too, deliberately attributed to a role
 *     ("School Administrator") rather than an invented name/school, so
 *     nobody mistakes them for real quotes. Swap in real ones once you
 *     have them — fabricated specific attributions (fake names, fake
 *     schools) would be actively misleading, generic role-based ones are
 *     an honest placeholder.
 *   - The hero's timetable visual is a hand-built CSS/SVG mockup, not a
 *     real screenshot — there's no production deployment to screenshot
 *     yet (see the deployment conversation). Swap for a real screenshot
 *     once the app is hosted somewhere presentable.
 */

const PRICING_TIERS = [
  {
    name: 'Starter',
    price: '₹1,999',
    period: '+ GST /month',
    tagline: 'For a single school finding its feet',
    features: ['1 school', 'Up to 500 students', 'Unlimited timetables', 'Email support'],
    highlighted: false,
  },
  {
    name: 'Growth',
    price: '₹4,999',
    period: '+ GST /month',
    tagline: 'For schools that need more hands on deck',
    features: ['1 school', 'Unlimited students', 'Multiple admins & viewers', 'Priority support'],
    highlighted: true,
  },
  {
    name: 'Group',
    price: 'Contact us',
    period: '',
    tagline: 'For a group running several schools',
    features: ['Multiple schools', 'Everything in Growth', 'Dedicated onboarding', 'Custom terms'],
    highlighted: false,
  },
]

const TESTIMONIALS = [
  {
    quote:
      "Building the timetable used to take our vice principal two full weeks every term. Typing in the rules and letting it solve took an afternoon.",
    role: 'School Administrator',
  },
  {
    quote:
      'The bit I didn\'t expect to matter: when it can\'t find a schedule, it tells you why. No more guessing which constraint is the problem.',
    role: 'Academic Coordinator',
  },
  {
    quote:
      "We locked the slots that were already working and let it fill in the rest. Didn't have to start from a blank grid.",
    role: 'School Administrator',
  },
]

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0 },
}

/**
 * A typewriter-style word cycler: types out each word in `words`
 * character by character, pauses, deletes it, then moves to the next
 * word and loops. Used in the Hero headline so it cycles through
 * "schools" / "colleges" / "institutions" instead of picking just one.
 */
function TypingWords({ words, typingSpeedMs = 90, deletingSpeedMs = 45, pauseMs = 1400, colorClassName = 'text-indigo-600' }) {
  const [wordIndex, setWordIndex] = useState(0)
  const [charCount, setCharCount] = useState(0)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    const currentWord = words[wordIndex]

    if (!deleting && charCount === currentWord.length) {
      const pause = setTimeout(() => setDeleting(true), pauseMs)
      return () => clearTimeout(pause)
    }

    if (deleting && charCount === 0) {
      setDeleting(false)
      setWordIndex((prev) => (prev + 1) % words.length)
      return
    }

    const timeout = setTimeout(
      () => setCharCount((prev) => prev + (deleting ? -1 : 1)),
      deleting ? deletingSpeedMs : typingSpeedMs
    )
    return () => clearTimeout(timeout)
  }, [charCount, deleting, wordIndex, words, typingSpeedMs, deletingSpeedMs, pauseMs])

  return (
    <span className={colorClassName}>
      {words[wordIndex].slice(0, charCount)}
      <span className="ml-0.5 inline-block w-0.5 animate-pulse bg-current align-middle" style={{ height: '0.85em' }} />
    </span>
  )
}


export default function LandingPage({ onGetStarted }) {
  return (
    <div className="min-h-screen bg-white text-neutral-900">
      <LandingNav onGetStarted={onGetStarted} />
      <Hero onGetStarted={onGetStarted} />
      <WorkflowDemo />
      <MetricsSection />
      <WhyChoose />
      {/* HowItWorks and Pricing removed for now (explicit request) — the
          component functions/data (STEPS, PRICING_TIERS) are left intact
          further down this file so they're a one-line add back rather
          than a rebuild once pricing is settled and this section is
          wanted again. */}
      <Testimonials />
      <Footer />
    </div>
  )
}

function LandingNav({ onGetStarted }) {
  return (
    <div className="sticky top-0 z-30 border-b border-white/10 bg-black">
      {/* No max-w-6xl/mx-auto here unlike the rest of the page's sections —
          that centers a fixed-width column and leaves equal, growing
          margins on both sides as the viewport widens, which is exactly
          why the logo never actually reached the true left edge like
          Papermark's header does. This bar instead spans the full width
          with fixed edge padding, so the logo and nav sit close to the
          real left edge on any screen size. */}
      <div className="flex items-center px-8 py-4 md:px-16 lg:px-28">
        {/* Wordmark + nav links grouped together on the left (Papermark-style
            layout) instead of the logo/nav/CTA being spread evenly across
            the bar with justify-between — the nav reads as belonging to
            the brand mark, not as a separate centered block. Plain
            wordmark now, no icon/box mark — Papermark's own header is just
            bold text too, no logomark next to it. */}
        <div className="flex items-center gap-10">
          <span className="text-[19px] font-bold tracking-tight text-white">Timetablz</span>
          <nav className="hidden items-center gap-8 text-[15px] text-neutral-300 md:flex">
            <a href="?page=why" className="hover:text-white">Why Timetablz</a>
            <a href="?page=pricing" className="hover:text-white">Plans and Pricing</a>
            <a href="?page=customers" className="hover:text-white">Customers</a>
            <a href="?page=about" className="hover:text-white">About</a>
            <a href="?page=support" className="hover:text-white">Support</a>
          </nav>
        </div>
        <div className="ml-auto flex items-center gap-6">
          <button onClick={onGetStarted} className="text-[15px] font-medium text-neutral-300 hover:text-white">
            Sign in
          </button>
          <button
            onClick={onGetStarted}
            className="rounded-md bg-white px-4 py-2 text-[15px] font-medium text-black hover:bg-neutral-200"
          >
            Get started free
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Faint single-stroke line-art scenes for the empty sides of the Hero —
 * replaces the earlier blurred-glow Spotlight treatment. Both sides are
 * built around the same subject as the product itself: a printed weekly
 * timetable pinned to the classroom wall, grid cells and all — not just a
 * generic classroom. `side="left"` shows a wall clock above a pinned
 * timetable chart, with a student desk and chair below it; `side="right"`
 * mirrors it with a teacher's desk whose laptop screen shows the same
 * grid in miniature, next to a second wall timetable and a stack of
 * books. Everything is `stroke`-only, no fill, at very low opacity — the
 * point is background texture, not an illustration anyone reads closely.
 * Hand-drawn with basic shapes rather than an icon library so it stays a
 * single dependency-free inline SVG.
 */
function HeroSideArt({ side, className = '' }) {
  const stroke = 'rgba(255,255,255,0.16)'
  const common = { fill: 'none', stroke, strokeWidth: 1.2, strokeLinecap: 'round', strokeLinejoin: 'round' }
  const gridStroke = { ...common, strokeWidth: 0.8 }

  // A pinned weekly-timetable chart: an outer frame, a heavier header
  // row, `cols` x `rows` grid cells, and two small "pin" dots at the top
  // corners as if it's tacked to a board — reused (at different sizes)
  // on both sides so the two scenes visibly share the same motif.
  function TimetableChart({ x, y, width, height, cols = 5, rows = 6 }) {
    const headerH = height / (rows + 1)
    const colW = width / cols
    return (
      <g>
        <rect x={x} y={y} width={width} height={height} rx="3" {...common} />
        <line x1={x} y1={y + headerH} x2={x + width} y2={y + headerH} {...common} />
        {Array.from({ length: rows - 1 }).map((_, i) => (
          <line
            key={`row-${i}`}
            x1={x}
            y1={y + headerH * (i + 2)}
            x2={x + width}
            y2={y + headerH * (i + 2)}
            {...gridStroke}
          />
        ))}
        {Array.from({ length: cols - 1 }).map((_, i) => (
          <line
            key={`col-${i}`}
            x1={x + colW * (i + 1)}
            y1={y}
            x2={x + colW * (i + 1)}
            y2={y + height}
            {...gridStroke}
          />
        ))}
        <circle cx={x + 10} cy={y - 6} r="3" {...common} />
        <circle cx={x + width - 10} cy={y - 6} r="3" {...common} />
      </g>
    )
  }

  return (
    <svg
      viewBox="0 0 320 640"
      className={`pointer-events-none absolute z-0 h-[640px] w-[320px] ${className}`}
      aria-hidden="true"
    >
      {side === 'left' ? (
        <>
          {/* Hanging pendant light */}
          <line x1="250" y1="0" x2="250" y2="70" {...common} />
          <path d="M225 70 Q250 52 275 70 L268 96 L232 96 Z" {...common} />

          {/* Wall clock */}
          <circle cx="90" cy="120" r="38" {...common} />
          <circle cx="90" cy="120" r="2.5" {...common} />
          <line x1="90" y1="120" x2="90" y2="98" {...common} />
          <line x1="90" y1="120" x2="106" y2="128" {...common} />

          {/* Pinned weekly timetable chart on the wall */}
          <TimetableChart x={30} y={195} width={220} height={190} cols={5} rows={6} />

          {/* Student desk + chair beneath it */}
          <path d="M45 470 L235 470 L220 495 L60 495 Z" {...common} />
          <line x1="65" y1="495" x2="65" y2="545" {...common} />
          <line x1="215" y1="495" x2="215" y2="545" {...common} />
          <path d="M105 470 L105 425 Q105 413 118 413 L138 413 Q151 413 151 425 L151 470" {...common} />

          {/* Floor line */}
          <line x1="0" y1="560" x2="320" y2="560" {...common} />
        </>
      ) : (
        <>
          {/* Hanging pendant light */}
          <line x1="70" y1="0" x2="70" y2="70" {...common} />
          <path d="M45 70 Q70 52 95 70 L88 96 L52 96 Z" {...common} />

          {/* Second, smaller wall timetable up top */}
          <TimetableChart x={140} y={110} width={150} height={120} cols={4} rows={5} />

          {/* Teacher's desk */}
          <path d="M30 460 L270 460 L250 490 L10 490 Z" {...common} />
          <line x1="35" y1="490" x2="35" y2="560" {...common} />
          <line x1="245" y1="490" x2="245" y2="560" {...common} />

          {/* Laptop on the desk, screen showing the same timetable grid in miniature */}
          <path d="M110 396 L210 396 L216 460 L104 460 Z" {...common} />
          <TimetableChart x={116} y={406} width={88} height={46} cols={4} rows={4} />
          <path d="M90 460 L230 460 L238 472 L82 472 Z" {...common} />

          {/* Stack of books beside the laptop */}
          <rect x="20" y="452" width="60" height="9" rx="2" {...common} />
          <rect x="24" y="443" width="52" height="9" rx="2" {...common} />
          <rect x="20" y="434" width="60" height="9" rx="2" {...common} />

          {/* Floor line */}
          <line x1="0" y1="560" x2="320" y2="560" {...common} />
        </>
      )}
    </svg>
  )
}

function Hero({ onGetStarted }) {
  return (
    <section className="relative overflow-hidden bg-black">
      {/* Faint line-art filling the empty sides of the centered hero — the
          reference the user sent (a hospitality SaaS hero) uses extremely
          faint single-stroke line drawings of an office scene instead of a
          blurred glow; this is the same idea adapted to our own subject
          matter (a classroom on the left, a teacher's desk with a laptop
          showing a little timetable grid on the right) rather than reusing
          someone else's illustration. Pure line art, no fill, opacity kept
          low enough to read as texture rather than content. Hidden below
          `lg` since there's no room for them once the hero text wraps. */}
      <HeroSideArt side="left" className="-left-16 top-0 hidden lg:block xl:-left-4" />
      <HeroSideArt side="right" className="-right-16 top-0 hidden lg:block xl:-right-4" />

      <div className="relative mx-auto max-w-3xl px-6 py-24 text-center md:py-32">
        <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.6 }}>
          {/* The cycling word sits on its own dedicated line (explicit <br/>,
              not just wrapping wherever it happens to land) so its
              changing width can never push "Instant timetables" onto an
              extra line — see the earlier version of this component for
              the layout-shift bug this avoids. */}
          <h1 className="font-serif text-5xl font-medium leading-[1.05] tracking-tight text-white md:text-6xl">
            Instant timetables
            <br />
            for <TypingWords words={['schools', 'colleges', 'institutions']} colorClassName="text-white" />
          </h1>
          <p className="mx-auto mt-5 max-w-lg text-lg text-neutral-400">
            Describe your scheduling rules in plain English and get a complete, ready-to-use
            timetable for every section and every teacher, with zero clashes.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={onGetStarted}
              className="rounded-full bg-white px-6 py-3 text-sm font-medium text-black hover:bg-neutral-200"
            >
              Get started free
            </button>
            <a
              href="#features"
              className="rounded-full border border-neutral-600 px-6 py-3 text-sm font-medium text-white hover:bg-neutral-900"
            >
              See how it works
            </a>
          </div>
          <p className="mt-4 text-xs text-neutral-500">No credit card required to try it.</p>
        </motion.div>
      </div>

      {/* Matches Papermark's actual bottom bar exactly now, per explicit
          correction: no label text at all, a revolving/scrolling row of
          customer names (their logos, our text), and an "Our Customers"
          button pinned to the right — not centered, static text. With
          one real school instead of six logos, the single name is
          repeated several times in the scrolling track (separated by a
          small dot) rather than looping one lonely item across the full
          width, which is what produced the empty-looking gaps before;
          this way the marquee track is actually full, same trick real
          sites use when they don't have enough distinct logos yet to
          fill a scroll. "Our Customers" links to the dedicated
          CustomersPage.jsx (`?page=customers`), same as Papermark's own
          button does for them. Content spans the full page width now
          (no `max-w-6xl`/`mx-auto` cap) rather than sitting in a
          narrower centered column with black margins either side, and
          the bar itself is `neutral-900` (a visibly grey shade) instead
          of the near-black `neutral-950` it was, both per explicit
          feedback that the narrower/blacker version looked congested. */}
      <div className="relative border-t border-white/10 bg-neutral-900 py-5">
        <div className="flex items-center gap-6 px-6 sm:px-10 lg:px-16">
          <div className="min-w-0 flex-1 [mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)]">
            <Marquee
              items={
                <span className="flex items-center gap-6 px-3 text-sm font-bold uppercase tracking-wide text-neutral-300">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Fragment key={i}>
                      <span>Shishya Public School, Dehradun</span>
                      <span className="text-neutral-600">•</span>
                    </Fragment>
                  ))}
                </span>
              }
              speed={26}
            />
          </div>
          <a
            href="?page=customers"
            className="shrink-0 rounded-md border border-white/20 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
          >
            Our Customers
          </a>
        </div>
      </div>
    </section>
  )
}

/**
 * A hand-built visual, not a real screenshot (see this file's top
 * docstring) — a small animated grid that suggests the actual product's
 * By Section timetable view without claiming to BE it.
 */
function TimetableMockup() {
  const rows = ['P1', 'P2', 'P3', 'P4', 'P5']
  const cols = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
  const subjects = ['Math', 'Science', 'English', 'PE', 'Art', 'History', 'Music']
  const colors = ['bg-indigo-600', 'bg-emerald-600', 'bg-amber-500', 'bg-sky-600', 'bg-violet-600']

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-4 shadow-xl shadow-black/40">
      <div className="mb-3 flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
        <span className="ml-2 text-xs text-neutral-400">Grade 8 · Section A</span>
      </div>
      <div className="grid grid-cols-[36px_repeat(5,1fr)] gap-1 text-[10px]">
        <div />
        {cols.map((c) => (
          <div key={c} className="pb-1 text-center font-medium text-neutral-500">
            {c}
          </div>
        ))}
        {rows.map((r, ri) => (
          <Fragment key={r}>
            <div className="flex items-center text-neutral-500">{r}</div>
            {cols.map((c, ci) => (
              <motion.div
                key={`${r}-${c}`}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: (ri * 5 + ci) * 0.02, duration: 0.3 }}
                className={`${colors[(ri + ci) % colors.length]} rounded px-1 py-1.5 text-center font-medium text-white`}
              >
                {subjects[(ri * 5 + ci * 3) % subjects.length]}
              </motion.div>
            ))}
          </Fragment>
        ))}
      </div>
    </div>
  )
}

// The exact example phrase used throughout docs/GETTING_STARTED.md's walk-
// through of the Constraints tab ("try typing something like...") — reused
// here verbatim so the demo below shows the real product's actual copy
// and workflow, not an invented example.
const DEMO_CONSTRAINT = 'Priya Sharma can only teach 10 periods a week'

const DEMO_NAV_ITEMS = ['Data Entry', 'Constraints', 'Timetable']

// Shown during the new 'setup' phase — a Data Entry tab was in
// DEMO_NAV_ITEMS but never actually got a turn in the demo (it only ever
// toggled between Constraints and Timetable), so the loop looked like it
// was skipping one of the three real product areas. This gives it one.
const DEMO_SETUP_ITEMS = ['Grade 8 · Section A (32 students)', 'Mathematics (6 periods/week)', 'Priya Sharma · Mathematics']

/**
 * Replaces the old text-plus-icon-cards Features() section with a single,
 * looping, silent product demo — no headline, no body copy, just the
 * actual workflow (set up a section → type a rule in plain English →
 * generate → get a clash-free grid) animating on repeat. Modeled on how
 * roommaster.com and relume.io use a real-interface-driven hero/section
 * animation instead of a static screenshot or a wall of feature text.
 *
 * Kept strictly black/white/grey (no colored badges or traffic-light
 * dots) to match the rest of the site's Papermark/Griffin-inspired
 * monochrome theme — the first version of this demo used emerald/indigo/
 * amber accent colors, which read as inconsistent with everything else
 * on the page after the black/white pass elsewhere.
 *
 * Built as a small state machine (`phase`) driven by chained setTimeouts,
 * the same pattern as TypingWords above — each phase schedules the next
 * one, and the final phase resets back to 'setup' so it loops forever.
 * AnimatePresence handles the cross-fade between phases; ResultGrid's own
 * staggered cell animation replays every loop because its key changes on
 * every remount.
 */
function WorkflowDemo() {
  const [phase, setPhase] = useState('setup') // 'setup' | 'typing' | 'added' | 'generating' | 'result'
  const [charCount, setCharCount] = useState(0)
  const [setupCount, setSetupCount] = useState(0)

  useEffect(() => {
    if (phase !== 'setup') return
    if (setupCount < DEMO_SETUP_ITEMS.length) {
      const t = setTimeout(() => setSetupCount((c) => c + 1), 500)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => setPhase('typing'), 700)
    return () => clearTimeout(t)
  }, [phase, setupCount])

  useEffect(() => {
    if (phase !== 'typing') return
    if (charCount < DEMO_CONSTRAINT.length) {
      const t = setTimeout(() => setCharCount((c) => c + 1), 42)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => setPhase('added'), 750)
    return () => clearTimeout(t)
  }, [phase, charCount])

  useEffect(() => {
    if (phase === 'added') {
      const t = setTimeout(() => setPhase('generating'), 1300)
      return () => clearTimeout(t)
    }
    if (phase === 'generating') {
      const t = setTimeout(() => setPhase('result'), 1500)
      return () => clearTimeout(t)
    }
    if (phase === 'result') {
      const t = setTimeout(() => {
        setCharCount(0)
        setSetupCount(0)
        setPhase('setup')
      }, 3200)
      return () => clearTimeout(t)
    }
  }, [phase])

  const activeNav =
    phase === 'setup' ? 'Data Entry' : phase === 'generating' || phase === 'result' ? 'Timetable' : 'Constraints'

  return (
    <section id="features" className="mx-auto max-w-6xl px-6 py-24">
      <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-sm">
        {/* Fake browser chrome — grounds this as "the actual app", the
            same trick both reference videos use (a real address bar
            framing the interface being demoed). Grey dots, not the usual
            red/amber/green traffic lights — same "less decorative, more
            deliberate" call made on LandingNav's wordmark earlier. */}
        <div className="flex items-center gap-2 border-b border-neutral-100 bg-neutral-50 px-5 py-3.5">
          <span className="h-2.5 w-2.5 rounded-full bg-neutral-300" />
          <span className="h-2.5 w-2.5 rounded-full bg-neutral-300" />
          <span className="h-2.5 w-2.5 rounded-full bg-neutral-300" />
          <div className="ml-3 max-w-xs flex-1 truncate rounded-md border border-neutral-200 bg-white px-3 py-1.5 text-[13px] text-neutral-400">
            timetablz.com
          </div>
        </div>

        <div className="flex">
          <div className="hidden w-48 shrink-0 border-r border-neutral-100 bg-neutral-50/60 p-5 sm:block">
            {DEMO_NAV_ITEMS.map((item) => (
              <div
                key={item}
                className={`mb-1.5 rounded-md px-3.5 py-2.5 text-sm font-medium transition-colors duration-300 ${
                  activeNav === item ? 'bg-neutral-900 text-white' : 'text-neutral-500'
                }`}
              >
                {item}
              </div>
            ))}
          </div>

          <div className="relative min-h-[420px] flex-1 p-10">
            <AnimatePresence mode="wait">
              {phase === 'setup' && (
                <motion.div
                  key="setup"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <p className="mb-3 text-sm font-medium text-neutral-500">Setting up your school</p>
                  <div className="space-y-2.5">
                    {DEMO_SETUP_ITEMS.map((item, i) => (
                      <AnimatePresence key={item}>
                        {setupCount > i && (
                          <motion.div
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.25 }}
                            className="flex items-center gap-2.5 rounded-lg border border-neutral-200 bg-white px-4 py-3 text-[14px] text-neutral-700"
                          >
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-neutral-900">
                              <path d="M20 6 9 17l-5-5" />
                            </svg>
                            {item}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    ))}
                  </div>
                </motion.div>
              )}

              {(phase === 'typing' || phase === 'added') && (
                <motion.div
                  key="constraints"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <p className="mb-2.5 text-sm font-medium text-neutral-500">Describe a scheduling rule</p>
                  <div className="rounded-lg border border-neutral-200 bg-white px-5 py-4 text-[15px] text-neutral-800">
                    {DEMO_CONSTRAINT.slice(0, charCount)}
                    <span className="ml-0.5 inline-block h-4 w-0.5 translate-y-0.5 animate-pulse bg-neutral-400 align-middle" />
                  </div>
                  <AnimatePresence>
                    {phase === 'added' && (
                      <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3 }}
                        className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 6 9 17l-5-5" />
                        </svg>
                        Availability rule added
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              )}

              {phase === 'generating' && (
                <motion.div
                  key="generating"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className="flex h-full flex-col items-center justify-center gap-3 py-20"
                >
                  <motion.div
                    className="h-9 w-9 rounded-full border-2 border-neutral-200 border-t-neutral-900"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
                  />
                  <p className="text-sm font-medium text-neutral-500">Generating timetable…</p>
                </motion.div>
              )}

              {phase === 'result' && (
                <motion.div
                  key="result"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <div className="mb-4 flex items-center justify-between">
                    <p className="text-sm font-medium text-neutral-500">Grade 8 · Section A</p>
                    <motion.span
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: 0.3, duration: 0.25 }}
                      className="inline-flex items-center gap-1 rounded-full bg-neutral-900 px-3 py-1 text-[13px] font-medium text-white"
                    >
                      Zero clashes
                    </motion.span>
                  </div>
                  <ResultGrid />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  )
}

/**
 * The "generated timetable" grid shown in WorkflowDemo's result phase —
 * light-theme sibling of TimetableMockup further down this file, sized
 * and paced for a section that loops every few seconds rather than
 * playing once on scroll-into-view.
 */
function ResultGrid() {
  const rows = ['P1', 'P2', 'P3', 'P4']
  const cols = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
  const subjects = ['Math', 'Science', 'English', 'PE', 'Art', 'History']
  // Round-robin subject color coding, one very lightly tinted color per
  // subject (bg-*-50, not -100) — the rest of WorkflowDemo (sidebar,
  // buttons, badges, spinner) stayed black/white/neutral per explicit
  // "keep the edgy black and white theme" feedback; this grid is the one
  // deliberate exception, since each subject reading at a glance the way
  // a real printed timetable uses color is worth the one departure from
  // the page's monochrome rule elsewhere.
  const SUBJECT_COLORS = {
    Math: { bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-100' },
    Science: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-100' },
    English: { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-100' },
    PE: { bg: 'bg-sky-50', text: 'text-sky-700', border: 'border-sky-100' },
    Art: { bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-100' },
    History: { bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-100' },
  }

  return (
    <div className="grid grid-cols-[36px_repeat(5,1fr)] gap-2 text-[11px]">
      <div />
      {cols.map((c) => (
        <div key={c} className="pb-1 text-center font-medium text-neutral-400">
          {c}
        </div>
      ))}
      {rows.map((r, ri) => (
        <Fragment key={r}>
          <div className="flex items-center text-neutral-400">{r}</div>
          {cols.map((c, ci) => {
            const subject = subjects[(ri * 5 + ci * 3) % subjects.length]
            const color = SUBJECT_COLORS[subject]
            return (
              <motion.div
                key={`${r}-${c}`}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: (ri * 5 + ci) * 0.03, duration: 0.3 }}
                className={`rounded-md border px-1.5 py-2 text-center font-semibold ${color.bg} ${color.text} ${color.border}`}
              >
                {subject}
              </motion.div>
            )
          })}
        </Fragment>
      ))}
    </div>
  )
}

// ⚠️ PLACEHOLDER METRICS — NOT REAL. Timetablz has exactly one real
// customer (Shishya Public School, Dehradun; see Hero's trust strip) as
// of when this was written. These numbers were requested explicitly as
// stand-in/mockup content while the site isn't live yet, with an explicit
// plan to replace them with real figures once there's an actual school
// roster to report on (see the founder conversation this was built
// alongside). DO NOT ship this section to production without swapping
// these for real, verifiable numbers first — publishing fabricated
// customer/usage counts on a live site is a false-advertising risk, not
// just a copy nitpick.
const CAPABILITY_STATS = [
  { n: '01', label: 'Schools serviced', value: '100+', unit: 'across India' },
  { n: '02', label: 'Teachers scheduled', value: '1,000+', unit: 'and counting' },
  { n: '03', label: 'Students scheduled', value: '10,000+', unit: 'every term' },
  { n: '04', label: 'Hours saved', value: '200+', unit: 'per school, per term' },
]

/**
 * A big-number stats section modeled on Papermark's "Total deal value
 * running through Papermark. $55,000,000,000" pattern. See the loud
 * comment on CAPABILITY_STATS above — these are placeholder numbers, not
 * real usage data, by explicit instruction while the site is still
 * pre-launch. Swap the headline number and the four columns for real
 * figures before this section ever reaches production.
 */
function MetricsSection() {
  return (
    <section className="border-t border-neutral-100 bg-white px-6 py-24">
      <div className="mx-auto max-w-6xl">
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
        >
          <p className="text-2xl text-neutral-900 md:text-3xl">
            Students already being scheduled with Timetablz.
          </p>
          <p className="mt-4 text-7xl font-semibold tracking-tight text-neutral-900 tabular-nums md:text-8xl">
            10,000+
          </p>
        </motion.div>

        <div className="mt-10 text-[13px] uppercase tracking-wide text-neutral-500">
          100+ schools across India trust Timetablz
        </div>

        {/* Stacks with horizontal divider rules below `lg` (a vertical-line
            grid only reads cleanly with all four in a single row — see
            Papermark's reference, which is a desktop-width screenshot),
            switches to Papermark's vertical-line-between-columns layout
            at `lg` via divide-x instead of a gap. */}
        <div className="mt-8 divide-y divide-neutral-200 border-t border-neutral-200 pt-8 lg:grid lg:grid-cols-4 lg:divide-y-0 lg:divide-x">
          {CAPABILITY_STATS.map((stat, i) => (
            <motion.div
              key={stat.n}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, amount: 0.3 }}
              variants={fadeUp}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              className="py-6 first:pt-0 lg:py-0 lg:px-8 lg:first:pl-0"
            >
              <p className="text-[13px] text-neutral-400">{stat.n}</p>
              <p className="mt-3 text-sm font-semibold uppercase tracking-wide text-neutral-900">{stat.label}</p>
              <p className="mt-4 text-4xl font-semibold tracking-tight text-neutral-900 tabular-nums">
                {stat.value}
                <span className="ml-1 text-sm font-normal normal-case text-neutral-400">{stat.unit}</span>
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

/**
 * A black/white/grey riff on the "Why hoteliers choose roommaster" pattern
 * from the reference screenshots: a serif headline, then a stack of large
 * soft rounded cards (some half-width, one full-width) each pairing a
 * short claim with a small supporting visual and a couple of floating
 * pill badges. Kept deliberately restrained relative to the reference —
 * one or two badges per card, muted geometry instead of a colorful
 * illustration — after earlier attempts at "decorative product graphics"
 * on this page read as cluttered (see FloatingTimetableCard's removal
 * further up the file's history). No invented performance numbers (no
 * "35% RevPAR"-style stat) since there's no usage data yet to back one —
 * see this file's top docstring on the same principle for pricing/
 * testimonials.
 */
/**
 * "Why schools choose Timetablz" — rebuilt a third time after actually
 * reading relume.ai's live DOM (getComputedStyle/getBoundingClientRect
 * on the real elements, not eyeballing screenshots or video frames).
 * That inspection found the earlier two rebuilds were both wrong about
 * what the section even is:
 *
 * - It is NOT scroll-scrubbed. Every image has `transform: none` inline
 *   and there is no scroll listener touching it — it's a plain static
 *   card, same as any other section on the page.
 * - Each card ("icon-tagline_card") is a light neutral card
 *   (rgb(241,240,238), 16px radius) with a bold, fully-saturated solid
 *   color image area on top (measured: rgb(255,159,255), a hot pink —
 *   not a pale tint) and an icon + heading + body row below.
 * - Inside that colored area sits a genuinely fine grid: 1.5px lines
 *   every 15px, drawn at low opacity in a slightly lighter shade of the
 *   same hue (rgba(255,223,255,0.5) inside a group at opacity .3) — not
 *   the loose 40px+ line grid used in the last two attempts.
 * - The screenshots themselves cascade in a straight diagonal staircase
 *   (measured delta: +45px right, -77px up per step going back in the
 *   stack), each one flat — no rotation, no box-shadow, only a small
 *   ~4.5px corner radius. The front-most tile sits lowest/left; each
 *   tile behind it is offset up-right and rendered at a lower z-index.
 *
 * Reproduced here as three static cards (Relume's own row is static
 * too), one per reason, each with a bold-accent image area holding a
 * diagonal 3-tile cascade built the same way, and an icon+heading+body
 * row beneath. Relume's tiles are real screenshots of real customer
 * sites; Timetablz doesn't have a library of those, so the two front
 * tiles render actual compact mockups of the product's own screens
 * (reusing the subject-color palette ResultGrid uses elsewhere on this
 * page) and the back-most barely-visible sliver is a plain color block,
 * matching how little of Relume's own back tiles are visible anyway.
 */
// All three cards cycle through the same three product screens, just
// starting at a different point in the rotation, so the row as a whole
// is always mid-motion rather than all three changing in lockstep —
// the "always something visibly happening" quality Relume's own homepage
// has elsewhere (its hero canvas continuously cycles between different
// real site builds), even though this particular static card of theirs
// doesn't animate on its own.
const SCREEN_TYPES = ['dataEntry', 'constraints', 'timetable']

const WHY_POINTS = [
  {
    heading: 'Turns weeks of work into an afternoon',
    body: "Type your scheduling rules as plain sentences instead of wrestling with spreadsheet formulas. The solver builds every section's timetable at once.",
    startIndex: 0,
    accent: 'indigo',
    icon: 'clock',
  },
  {
    heading: 'Built around how schools actually run',
    body: 'Not a generic scheduler with "school" bolted on. Periods, sections, subject-load limits, and teacher availability are first-class from day one.',
    startIndex: 1,
    accent: 'emerald',
    icon: 'building',
  },
  {
    heading: 'One connected workflow',
    body: 'Data entry, constraints, generation, fine-tuning, and export all live in one place. No juggling a spreadsheet, a messaging thread, and a printed draft separately.',
    startIndex: 2,
    accent: 'amber',
    icon: 'link',
  },
]

// Bold, fully-saturated per-point colors (measured Relume equivalent:
// rgb(255,159,255) solid, not a pale bg-*-50/100 tint) plus a lighter
// tint of the same hue for the grid lines and the back-most cascade
// tile, and the usual light tint/text pairing for the icon chip in the
// card body below the image.
const ACCENT_STYLES = {
  indigo: { solid: 'bg-indigo-500', hex: '#6366f1', gridRgba: 'rgba(255,255,255,0.35)', backTile: 'bg-indigo-300', tint: 'bg-indigo-100', text: 'text-indigo-600' },
  emerald: { solid: 'bg-emerald-500', hex: '#10b981', gridRgba: 'rgba(255,255,255,0.35)', backTile: 'bg-emerald-300', tint: 'bg-emerald-100', text: 'text-emerald-600' },
  amber: { solid: 'bg-amber-500', hex: '#f59e0b', gridRgba: 'rgba(255,255,255,0.35)', backTile: 'bg-amber-300', tint: 'bg-amber-100', text: 'text-amber-600' },
}

// Same very light subject tints ResultGrid uses lower down this page,
// kept as its own small copy since that one is scoped inside
// ResultGrid's own function body.
const SCREEN_SUBJECT_COLORS = {
  Math: { bg: 'bg-indigo-50', text: 'text-indigo-700' },
  Science: { bg: 'bg-emerald-50', text: 'text-emerald-700' },
  English: { bg: 'bg-amber-50', text: 'text-amber-700' },
  PE: { bg: 'bg-sky-50', text: 'text-sky-700' },
}

const POINT_ICONS = {
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" />
    </>
  ),
  building: (
    <>
      <path d="M4 21V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v16" />
      <path d="M14 21V9a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v12" />
      <path d="M8 8h0M8 12h0M8 16h0" />
    </>
  ),
  link: (
    <>
      <path d="M9 15l6-6" />
      <path d="M11 5l1-1a3.5 3.5 0 0 1 5 5l-1 1" />
      <path d="M13 19l-1 1a3.5 3.5 0 0 1-5-5l1-1" />
    </>
  ),
}

// One compact mockup per screen type, sized to sit inside a small
// cascade tile (no browser chrome, no address bar — Relume's own tiles
// are raw screenshots with nothing framing them, so these match that
// rather than the browser-window treatment earlier drafts added).
function MiniScreen({ type, accent }) {
  if (type === 'dataEntry') {
    const teachers = [
      ['Priya Sharma', 'Mathematics'],
      ['Arjun Mehta', 'Science'],
    ]
    return (
      <div className="space-y-1.5">
        <p className="text-[10px] font-semibold text-neutral-900">Teachers</p>
        {teachers.map(([name, subject]) => (
          <div key={name} className="flex items-center gap-1.5 rounded bg-neutral-50 px-1.5 py-1">
            <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${ACCENT_STYLES[accent].solid} text-[7px] font-semibold text-white`}>
              {name.split(' ').map((n) => n[0]).join('')}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[9px] font-medium text-neutral-800">{name}</p>
              <p className="truncate text-[8px] text-neutral-400">{subject}</p>
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (type === 'constraints') {
    return (
      <div className="space-y-1.5">
        <p className="text-[10px] font-semibold text-neutral-900">Constraints</p>
        <div className="rounded bg-neutral-50 px-1.5 py-1.5 text-[8.5px] leading-snug text-neutral-600">
          "Priya can only teach mornings"
        </div>
        <div className="flex flex-wrap gap-1">
          <span className="rounded-full border border-neutral-200 px-1.5 py-0.5 text-[7.5px] text-neutral-500">No back-to-back PE</span>
        </div>
      </div>
    )
  }

  // 'timetable'
  const grid = [
    ['Math', 'Science'],
    ['English', 'PE'],
  ]
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold text-neutral-900">Grade 8 · Section A</p>
      <div className="grid grid-cols-2 gap-1">
        {grid.flat().map((subject, i) => {
          const s = SCREEN_SUBJECT_COLORS[subject]
          return (
            <div key={i} className={`rounded px-1.5 py-1.5 text-center text-[8.5px] font-medium ${s.bg} ${s.text}`}>
              {subject}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Base (stacked) and hover (spread) positions for the three cascade
// tiles, as percentages of the stage box. Hovering fans the stack apart
// — the back tile slides further up-right, the front tile further
// down-left — a concrete, tactile bit of interactivity on top of the
// content auto-cycling below, rather than motion for its own sake.
const TILE_LAYOUT = {
  back: {
    rest: { left: '36%', top: '8%', width: '62%', height: '42%' },
    hover: { left: '46%', top: '0%', width: '58%', height: '40%' },
  },
  mid: {
    rest: { left: '20%', top: '24%', width: '64%', height: '44%' },
    hover: { left: '16%', top: '22%', width: '62%', height: '42%' },
  },
  front: {
    rest: { left: '3%', top: '45%', width: '70%', height: '48%' },
    hover: { left: '-5%', top: '52%', width: '68%', height: '46%' },
  },
}

// The image area: a bold solid-accent field, a fine 15px-pitch grid
// drawn on top (matching the measured Relume grid exactly, scaled to
// this container, and slowly panning so the field never sits perfectly
// still), and a diagonal three-tile cascade — back-most tile a plain
// color block, then two screen mockups, flat (no rotation, no shadow),
// tight ~5px corners. The two content tiles auto-cycle through all
// three product screens on a loop, crossfading, and the whole stack
// fans apart on hover.
function CascadeStage({ startIndex, accent }) {
  const a = ACCENT_STYLES[accent]
  const [cycle, setCycle] = useState(startIndex)
  const [hovered, setHovered] = useState(false)

  useEffect(() => {
    const id = setInterval(() => setCycle((v) => (v + 1) % SCREEN_TYPES.length), 3200)
    return () => clearInterval(id)
  }, [])

  const back = SCREEN_TYPES[cycle]
  const mid = SCREEN_TYPES[(cycle + 1) % SCREEN_TYPES.length]
  const front = SCREEN_TYPES[(cycle + 2) % SCREEN_TYPES.length]

  return (
    <div
      className="relative aspect-[5/4] overflow-hidden rounded-t-2xl bg-neutral-900"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <motion.div
        className="absolute inset-0"
        style={{
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.14) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.14) 1px, transparent 1px)',
          backgroundSize: '15px 15px',
        }}
        animate={{ backgroundPosition: ['0px 0px', '15px 15px'] }}
        transition={{ duration: 6, repeat: Infinity, ease: 'linear' }}
      />

      <motion.div
        className={`absolute rounded-[5px] ${a.backTile} opacity-90`}
        animate={hovered ? TILE_LAYOUT.back.hover : TILE_LAYOUT.back.rest}
        transition={{ type: 'spring', stiffness: 220, damping: 24 }}
      />

      <motion.div
        className="absolute overflow-hidden rounded-[5px] bg-white text-left"
        animate={hovered ? TILE_LAYOUT.mid.hover : TILE_LAYOUT.mid.rest}
        transition={{ type: 'spring', stiffness: 220, damping: 24 }}
      >
        <AnimatePresence>
          <motion.div
            key={mid}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="absolute inset-0 p-2.5"
          >
            <MiniScreen type={mid} accent={accent} />
          </motion.div>
        </AnimatePresence>
      </motion.div>

      <motion.div
        className="absolute overflow-hidden rounded-[5px] bg-white text-left"
        animate={hovered ? TILE_LAYOUT.front.hover : TILE_LAYOUT.front.rest}
        transition={{ type: 'spring', stiffness: 220, damping: 24 }}
      >
        <AnimatePresence>
          <motion.div
            key={front}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="absolute inset-0 p-3"
          >
            <MiniScreen type={front} accent={accent} />
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  )
}

function WhyCard({ point, index }) {
  const a = ACCENT_STYLES[point.accent]
  return (
    <motion.div
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.3 }}
      variants={fadeUp}
      transition={{ duration: 0.5, delay: index * 0.1 }}
      className="overflow-hidden rounded-2xl border border-neutral-200 bg-neutral-50"
    >
      <CascadeStage startIndex={point.startIndex} accent={point.accent} />
      <div className="p-7">
        <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${a.tint}`}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={a.text}>
            {POINT_ICONS[point.icon]}
          </svg>
        </span>
        <h3 className="mt-4 font-serif text-xl font-medium text-neutral-900">{point.heading}</h3>
        <p className="mt-2 text-[14.5px] leading-relaxed text-neutral-500">{point.body}</p>
      </div>
    </motion.div>
  )
}

function WhyChoose() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-24">
      <motion.h2
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, amount: 0.3 }}
        variants={fadeUp}
        transition={{ duration: 0.5 }}
        className="mx-auto max-w-3xl text-center font-serif text-4xl font-medium leading-tight tracking-tight text-neutral-900 md:text-5xl"
      >
        Why schools choose Timetablz
      </motion.h2>

      <div className="mt-14 grid gap-8 md:grid-cols-3">
        {WHY_POINTS.map((point, i) => (
          <WhyCard key={point.heading} point={point} index={i} />
        ))}
      </div>
    </section>
  )
}

const STEPS = [
  { n: '01', title: 'Set up your school', body: 'Periods, subjects, teachers, and sections: type them in or bulk-import a spreadsheet.' },
  { n: '02', title: 'Describe your rules', body: 'Plain-English constraints, scoped to a subject, teacher, day, or specific section.' },
  { n: '03', title: 'Generate', body: 'The solver builds every section\'s schedule at once, with zero teacher or room clashes.' },
  { n: '04', title: 'Fine-tune and export', body: 'Lock slots, drag to adjust, then export to Excel or PDF for the staff room wall.' },
]

function HowItWorks() {
  return (
    <section id="how-it-works" className="bg-slate-50/60 py-24">
      <div className="mx-auto max-w-6xl px-6">
        <motion.h2
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mb-14 text-center text-3xl font-semibold tracking-tight"
        >
          From blank slate to a full timetable
        </motion.h2>
        <div className="grid gap-8 md:grid-cols-4">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, amount: 0.3 }}
              variants={fadeUp}
              transition={{ duration: 0.4, delay: i * 0.1 }}
            >
              <div className="mb-3 text-2xl font-semibold text-slate-300">{s.n}</div>
              <h3 className="font-medium">{s.title}</h3>
              <p className="mt-2 text-sm text-slate-500">{s.body}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Pricing({ onGetStarted }) {
  return (
    <section id="pricing" className="mx-auto max-w-6xl px-6 py-24">
      <motion.div
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, amount: 0.3 }}
        variants={fadeUp}
        transition={{ duration: 0.5 }}
        className="mx-auto mb-10 max-w-2xl text-center"
      >
        <h2 className="text-3xl font-semibold tracking-tight">Simple pricing</h2>
        <p className="mt-3 text-slate-500">Pick what fits your school. Change or cancel anytime.</p>
      </motion.div>

      <div className="grid gap-6 md:grid-cols-3">
        {PRICING_TIERS.map((tier, i) => (
          <motion.div
            key={tier.name}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.3 }}
            variants={fadeUp}
            transition={{ duration: 0.4, delay: i * 0.1 }}
            className={`rounded-xl border p-7 ${
              tier.highlighted ? 'border-indigo-600 shadow-xl shadow-slate-200/60' : 'border-slate-200'
            }`}
          >
            {tier.highlighted && (
              <span className="mb-3 inline-block rounded-full bg-indigo-600 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white">
                Most popular
              </span>
            )}
            <h3 className="font-medium">{tier.name}</h3>
            <p className="mt-1 text-sm text-slate-500">{tier.tagline}</p>
            <div className="mt-5 flex items-baseline gap-1">
              <span className="text-3xl font-semibold">{tier.price}</span>
              <span className="text-sm text-slate-500">{tier.period}</span>
            </div>
            <ul className="mt-6 flex flex-col gap-2.5 text-sm text-slate-600">
              {tier.features.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <button
              onClick={onGetStarted}
              className={`mt-7 w-full rounded-md px-4 py-2.5 text-sm font-medium ${
                tier.highlighted
                  ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                  : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
              }`}
            >
              Get started
            </button>
          </motion.div>
        ))}
      </div>
    </section>
  )
}

// Different width ratios per tile (narrow/medium/wide) to match the
// uneven-column photo-grid look from the Papermark reference, rather than
// three equal boxes. Also a distinct dark gradient tone per tile, used as
// a stand-in for tiles that don't have a real photo yet — varying the
// gradient at least keeps those from reading as one flat repeated block.
// All three tiles now carry a real Shishya Public School photo (see the
// comment on the third entry — confirmed with the founder that the
// TESTIMONIALS quote text is still illustrative/placeholder, not
// something this school actually said). Pairing a real, identifiable
// photo with an invented quote would read as putting words in their
// mouth, so every photo tile overrides the quote with a plain factual
// caption instead (see the `image` check in the render below) rather
// than reusing TESTIMONIALS[i].quote/role. Note the entrance photo here
// and the third tile's photo are the same shot the founder uploaded
// twice — left as-is per the literal request, worth swapping one out for
// a distinct angle later if that's noticeable in the row.
const TESTIMONIAL_TILE_STYLES = [
  {
    flex: 'md:flex-[1]',
    gradient: 'from-neutral-800 to-neutral-950',
    image: shishyaPublicSchoolGatePhoto,
    caption: 'Shishya Public School, Dehradun',
    subcaption: 'Campus gate',
  },
  {
    flex: 'md:flex-[1.2]',
    gradient: 'from-neutral-700 to-neutral-950',
    image: shishyaPublicSchoolEntrancePhoto,
    caption: 'Shishya Public School, Dehradun',
    subcaption: 'Main building',
  },
  {
    flex: 'md:flex-[1.6]',
    gradient: 'from-neutral-800 via-neutral-900 to-black',
    image: shishyaPublicSchoolPhoto,
    caption: 'Shishya Public School, Dehradun',
    subcaption: 'One of the first schools using Timetablz',
  },
]

/**
 * Papermark-style "Real impact for real teams" photo-tile layout, applied
 * to this page's existing (already-honest — see TESTIMONIALS above,
 * role-only attribution, no invented names/schools) testimonials.
 *
 * The reference uses real photos of real customers/teams. Two of the
 * three tiles still don't have one (no photography of any other customer,
 * and no image-generation tool available in this session), so those stay
 * a plain dark gradient rather than a stock photo standing in for a real
 * one — swap each remaining gradient div for a real photo once one
 * exists, the overlay/quote positioning already works with either.
 */
function Testimonials() {
  return (
    <section id="customers" className="bg-black py-24">
      <div className="mx-auto max-w-6xl px-6">
        <motion.h2
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mb-10 font-serif text-3xl font-medium tracking-tight text-white md:text-4xl"
        >
          What schools are saying
        </motion.h2>
        <div className="flex flex-col gap-4 md:flex-row">
          {TESTIMONIALS.map((t, i) => {
            const style = TESTIMONIAL_TILE_STYLES[i % TESTIMONIAL_TILE_STYLES.length]
            return (
              // Hover motion is plain CSS (`group`/`group-hover:`), not a
              // framer-motion `whileHover` — this div already has a
              // `transition` prop driving its scroll-into-view fade/rise,
              // and framer applies one `transition` config to every
              // animation state including hover, which would wrongly
              // delay the hover response by `i * 0.1`s too. Keeping hover
              // as separate CSS transitions sidesteps that entirely.
              <motion.div
                key={t.role + i}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, amount: 0.3 }}
                variants={fadeUp}
                transition={{ duration: 0.4, delay: i * 0.1 }}
                className={`group relative min-h-[380px] flex-1 cursor-default overflow-hidden rounded-xl shadow-lg shadow-black/0 transition-all duration-300 ease-out hover:-translate-y-1.5 hover:shadow-black/40 ${style.flex}`}
              >
                {/* The "photo" (a real one where available, a gradient
                    stand-in otherwise) zooms in slightly on hover — the
                    same subtle Ken Burns-style effect Papermark's photo
                    tiles use — while the overlay and text stay put so the
                    caption/quote never jitters. */}
                {style.image ? (
                  <img
                    src={style.image}
                    alt={style.caption}
                    className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
                  />
                ) : (
                  <div
                    className={`absolute inset-0 bg-gradient-to-br ${style.gradient} transition-transform duration-500 ease-out group-hover:scale-110`}
                  />
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/10 to-transparent transition-colors duration-300 group-hover:from-black/95" />
                <div className="absolute bottom-0 left-0 right-0 p-6 transition-transform duration-300 ease-out group-hover:-translate-y-1">
                  {style.image ? (
                    <>
                      <p className="text-[15px] font-medium leading-snug text-white">{style.caption}</p>
                      <p className="mt-3 text-xs font-medium uppercase tracking-wide text-neutral-400 opacity-80 transition-opacity duration-300 group-hover:opacity-100">
                        {style.subcaption}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-[15px] font-medium leading-snug text-white">"{t.quote}"</p>
                      <p className="mt-3 text-xs font-medium uppercase tracking-wide text-neutral-400 opacity-80 transition-opacity duration-300 group-hover:opacity-100">
                        {t.role}
                      </p>
                    </>
                  )}
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

// Every link here goes somewhere real — an in-page anchor already used
// elsewhere on this page, a mailto, or one of the two legal pages built
// in LegalPage.jsx/PrivacyPolicyPage.jsx/TermsOfServicePage.jsx.
// Deliberately NOT padded out with Papermark's full column count (Use
// Cases, Alternatives, a blog, a help center, comparison pages, ...) —
// this site doesn't have any of that content, and a footer full of links
// to pages that don't exist would look broken rather than substantial.
const FOOTER_COLUMNS = [
  {
    // "How it works" link removed along with that section (see the render
    // comment above HowItWorks) — add back once it's wanted again. Pricing
    // now points at the standalone PricingPage.jsx (`?page=pricing`)
    // instead of the removed in-page `#pricing` anchor.
    heading: 'Product',
    links: [
      { label: 'Why Timetablz', href: '?page=why' },
      { label: 'Pricing', href: '?page=pricing' },
    ],
  },
  {
    // No "Contact us" mailto here yet — the business email/domain hasn't
    // been decided (see the founder conversation on domain naming), and a
    // mailto to a made-up address would silently bounce. Add it back once
    // that's settled.
    heading: 'Company',
    links: [
      { label: 'About', href: '?page=about' },
      { label: 'Customers', href: '?page=customers' },
      { label: 'Support', href: '?page=support' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy Policy', href: '?page=privacy' },
      { label: 'Terms of Service', href: '?page=terms' },
    ],
  },
]

function Footer() {
  return (
    <footer className="border-t border-white/10 bg-black py-16 text-neutral-400">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1fr_1fr]">
          <div>
            <span className="text-[17px] font-bold tracking-tight text-white">Timetablz</span>
            <p className="mt-3 max-w-[220px] text-sm leading-relaxed">
              Instant, clash-free timetables for schools and colleges.
            </p>
          </div>

          {FOOTER_COLUMNS.map((col) => (
            <div key={col.heading}>
              <p className="text-sm font-semibold text-white">{col.heading}</p>
              <ul className="mt-4 space-y-3 text-sm">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a href={link.href} className="hover:text-white">
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 border-t border-white/10 pt-6 text-xs">
          © {new Date().getFullYear()} Timetablz. All rights reserved.
        </div>
      </div>
    </footer>
  )
}
