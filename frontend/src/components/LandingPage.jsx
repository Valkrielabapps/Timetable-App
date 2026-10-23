import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Fragment, useEffect, useState } from 'react'
import shishyaPublicSchoolPhoto from '../assets/shishya-public-school.png'
import shishyaPublicSchoolGatePhoto from '../assets/shishya-public-school-gate.png'
import shishyaPublicSchoolEntrancePhoto from '../assets/shishya-public-school-entrance.png'
import SiteNav from './SiteNav'
import SiteFooter from './SiteFooter'

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
 * The hero's changing last word - "schools", "colleges", "institutions" -
 * typed out and deleted letter by letter, with a blinking cursor. Held still
 * on the first word for anyone whose device asks for reduced motion; the
 * heading's accessible name carries the full sentence either way.
 */
function TypingWords({ words, typingSpeedMs = 90, deletingSpeedMs = 45, pauseMs = 1400, colorClassName = 'text-white' }) {
  const reduceMotion = useReducedMotion()
  const [wordIndex, setWordIndex] = useState(0)
  const [charCount, setCharCount] = useState(0)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (reduceMotion) return undefined
    const currentWord = words[wordIndex]

    if (!deleting && charCount === currentWord.length) {
      const pause = setTimeout(() => setDeleting(true), pauseMs)
      return () => clearTimeout(pause)
    }

    if (deleting && charCount === 0) {
      setDeleting(false)
      setWordIndex((prev) => (prev + 1) % words.length)
      return undefined
    }

    const timeout = setTimeout(
      () => setCharCount((prev) => prev + (deleting ? -1 : 1)),
      deleting ? deletingSpeedMs : typingSpeedMs,
    )
    return () => clearTimeout(timeout)
  }, [reduceMotion, charCount, deleting, wordIndex, words, typingSpeedMs, deletingSpeedMs, pauseMs])

  const shown = reduceMotion ? words[0] : words[wordIndex].slice(0, charCount)
  return (
    <span className={colorClassName} aria-hidden="true">
      {shown}
      <span className="ml-0.5 inline-block w-0.5 animate-pulse bg-current align-middle" style={{ height: '0.85em' }} />
    </span>
  )
}


export default function LandingPage({ onGetStarted, onSignIn = onGetStarted, signedIn = false }) {
  return (
    <div className="min-h-screen bg-white text-neutral-900">
      <LandingNav onGetStarted={onGetStarted} onSignIn={onSignIn} signedIn={signedIn} />
      <Hero onGetStarted={onGetStarted} signedIn={signedIn} />
      <WorkflowDemo />
      <MetricsSection />
      <WhyChoose />
      {/* HowItWorks and Pricing removed for now (explicit request) — the
          component functions/data (STEPS, PRICING_TIERS) are left intact
          further down this file so they're a one-line add back rather
          than a rebuild once pricing is settled and this section is
          wanted again. The "What schools are saying" photo section
          (Testimonials) is hidden the same way - the function is still
          below, so putting <Testimonials /> back here restores it. */}
      <ClosingCta onGetStarted={onGetStarted} signedIn={signedIn} />
      <SiteFooter />
    </div>
  )
}

function LandingNav({ onGetStarted, onSignIn, signedIn }) {
  // The shared site bar (SiteNav) - the same one every public page shows.
  return <SiteNav signedIn={signedIn} onGetStarted={onGetStarted} onSignIn={onSignIn} />
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

function Hero({ onGetStarted, signedIn }) {
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
          <h1
            aria-label="Instant timetables for schools and colleges"
            className="font-serif text-5xl font-medium leading-[1.05] tracking-tight text-white md:text-6xl"
          >
            <span aria-hidden="true">Instant timetables</span>
            <br />
            <span aria-hidden="true">for </span>
            <TypingWords words={['schools', 'colleges', 'institutions']} />
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
              {signedIn ? 'Go to your dashboard' : 'Get started free'}
            </button>
            <a
              href="#features"
              className="rounded-full border border-neutral-600 px-6 py-3 text-sm font-medium text-white hover:bg-neutral-900"
            >
              See how it works
            </a>
          </div>
          <p className="mt-4 text-sm text-neutral-400">No credit card required to try it.</p>
        </motion.div>
      </div>

      {/* One customer, said once and plainly. Scrolling the same name across
          the bar a dozen times made it obvious there was only one; a single
          honest line reads as confident instead. Add names here as schools
          sign on, and bring back a scrolling strip at four or five. */}
      <div className="relative border-t border-white/10 bg-neutral-900 py-5">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-6 gap-y-3 px-6 text-sm">
          <span className="text-neutral-400">Already building timetables at</span>
          <span className="font-semibold uppercase tracking-wide text-white">Shishya Public School, Dehradun</span>
          <a
            href="?page=customers"
            className="inline-flex items-center gap-1.5 font-medium text-neutral-300 underline-offset-4 hover:text-white hover:underline"
          >
            Read their story
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
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

// The same step names as the Why Timetablz page.
const DEMO_NAV_ITEMS = ['Your school', 'Your rules', 'Your timetable']

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
 * the same self-scheduling pattern as a typewriter effect — each phase schedules the next
 * one, and the final phase resets back to 'setup' so it loops forever.
 * AnimatePresence handles the cross-fade between phases; ResultGrid's own
 * staggered cell animation replays every loop because its key changes on
 * every remount.
 */
function WorkflowDemo() {
  // Opens on the finished timetable, so whoever scrolls here first sees the
  // result - not a spinner in an empty box, which read as a broken page.
  const [phase, setPhase] = useState('result') // 'setup' | 'typing' | 'added' | 'generating' | 'result'
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
      const t = setTimeout(() => setPhase('result'), 900)
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
    phase === 'setup' ? 'Your school' : phase === 'generating' || phase === 'result' ? 'Your timetable' : 'Your rules'

  return (
    <section id="features" className="mx-auto max-w-6xl px-6 pb-14 pt-20">
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

          <div className="relative min-h-[380px] flex-1 p-6 sm:p-10">
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
                  <p className="text-sm font-medium text-neutral-500">Building every section at once…</p>
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

// Product facts only - each one is true of every school on day one. The
// earlier "100+ schools / 10,000+ students" figures were placeholders, and a
// usage claim goes back here only once there are real numbers to report.
const CAPABILITY_STATS = [
  { n: '01', label: 'Generation time', value: 'Seconds', unit: 'for a whole school' },
  { n: '02', label: 'Teacher and room clashes', value: '0', unit: 'in every timetable' },
  { n: '03', label: 'Rules', value: 'Plain English', unit: 'no formulas or settings' },
  { n: '04', label: 'Exports', value: 'Excel & PDF', unit: 'every class and teacher' },
]

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
            Clashes in a timetable built by Timetablz.
          </p>
          <p className="mt-4 text-7xl font-semibold tracking-tight text-neutral-900 tabular-nums md:text-8xl">
            Zero<span className="text-emerald-600">.</span>
          </p>
        </motion.div>

        <div className="mt-10 text-[13px] uppercase tracking-wide text-neutral-500">
          Every section and every teacher, solved together
        </div>

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
              <p className="text-[13px] text-neutral-500">{stat.n}</p>
              <p className="mt-3 text-sm font-semibold uppercase tracking-wide text-neutral-900">{stat.label}</p>
              <p className="mt-4 text-3xl font-semibold tracking-tight text-neutral-900">{stat.value}</p>
              <p className="mt-1 text-sm text-neutral-500">{stat.unit}</p>
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
 * "Why schools choose Timetablz", laid out like Sequoia's "one integrated
 * platform" section: a centred headline and paragraph, a product mock-up in
 * the middle, and two benefits either side of it. On a phone the mock-up
 * comes first and the benefits stack beneath it.
 *
 * Every benefit is a real property of the product - no invented numbers.
 * The mock-up is drawn in HTML rather than a screenshot so it stays crisp
 * and matches the app's real palette.
 */
const WHY_BENEFITS = {
  left: [
    {
      title: 'Timetables in minutes, not weeks',
      body: 'The whole school is solved at once, every section and every teacher together, usually in under a minute.',
    },
    {
      title: 'Zero clashes, guaranteed',
      body: 'No teacher or room is ever double-booked. Clashes are ruled out while the timetable is built, not found later on the staff room wall.',
    },
  ],
  right: [
    {
      title: 'Rules in plain English',
      body: "Type rules the way you'd say them, like \"no PE right after lunch\". You see exactly how each one was read before it's applied.",
    },
    {
      title: 'Ready to share',
      body: 'Lock the slots that already work, regenerate the rest, and export every class and teacher timetable to Excel or PDF.',
    },
  ],
}

function WhyBenefit({ title, body, delay }) {
  return (
    <motion.div
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.4 }}
      variants={fadeUp}
      transition={{ duration: 0.5, delay }}
      className="max-w-[240px]"
    >
      <h3 className="text-[17px] font-semibold leading-snug text-neutral-900">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-neutral-500">{body}</p>
    </motion.div>
  )
}

const MOCK_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
// [subject, tint] per period, one row per period - a believable Grade 9 week.
const MOCK_SUBJECTS = {
  Maths: 'bg-emerald-100 text-emerald-900',
  English: 'bg-sky-100 text-sky-900',
  Physics: 'bg-violet-100 text-violet-900',
  Hindi: 'bg-amber-100 text-amber-900',
  Biology: 'bg-rose-100 text-rose-900',
  PE: 'bg-lime-100 text-lime-900',
  Chemistry: 'bg-indigo-100 text-indigo-900',
}
const MOCK_WEEK = [
  ['Maths', 'English', 'Physics', 'Maths', 'Hindi'],
  ['English', 'Maths', 'Chemistry', 'Biology', 'Maths'],
  ['Physics', 'Hindi', 'Maths', 'English', 'Chemistry'],
  ['Biology', 'PE', 'English', 'Physics', 'English'],
  ['Hindi', 'Chemistry', 'Biology', 'PE', 'Physics'],
]

function WhyMockup() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.6 }}
      className="relative mx-auto w-full max-w-[460px]"
    >
      <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-[0_30px_80px_-30px_rgba(16,24,40,0.35)]">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[13px] font-semibold text-neutral-900">Grade 9 · Section A</p>
            <p className="text-[11px] text-neutral-400">Week timetable</p>
          </div>
          <span className="flex items-center gap-1.5 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            No clashes
          </span>
        </div>

        <div className="mt-3 flex gap-1.5 text-[10px]">
          <span className="rounded-full bg-neutral-900 px-2.5 py-1 font-medium text-white">By section</span>
          <span className="rounded-full bg-neutral-100 px-2.5 py-1 text-neutral-500">By teacher</span>
          <span className="rounded-full bg-neutral-100 px-2.5 py-1 text-neutral-500">Substitutions</span>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2">
          {[
            ['Sections', '14'],
            ['Teachers', '33'],
            ['Generated in', '4 sec'],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-neutral-100 bg-neutral-50 px-2.5 py-2">
              <p className="text-[9px] uppercase tracking-wide text-neutral-400">{label}</p>
              <p className="mt-0.5 text-lg font-semibold tracking-tight text-neutral-900">{value}</p>
            </div>
          ))}
        </div>

        <div className="mt-3 overflow-hidden rounded-xl border border-neutral-100">
          <div className="grid grid-cols-[40px_repeat(5,1fr)] bg-neutral-50 text-[9px] font-medium uppercase tracking-wide text-neutral-400">
            <span />
            {MOCK_DAYS.map((d) => (
              <span key={d} className="py-1.5 text-center">{d}</span>
            ))}
          </div>
          {MOCK_WEEK.map((row, p) => (
            <div key={p} className="grid grid-cols-[40px_repeat(5,1fr)] gap-1 border-t border-neutral-100 px-1 py-1">
              <span className="self-center text-center text-[9px] text-neutral-400">P{p + 1}</span>
              {row.map((subject, d) => (
                <span
                  key={d}
                  className={`truncate rounded-md px-1 py-1.5 text-center text-[9.5px] font-medium ${MOCK_SUBJECTS[subject]}`}
                >
                  {subject}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
      {/* Fades the bottom of the card into the section, as in the reference. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 rounded-b-2xl bg-gradient-to-t from-[#f3faf6] to-transparent" />
    </motion.div>
  )
}

function WhyChoose() {
  return (
    <section className="bg-gradient-to-b from-white to-[#f3faf6] px-6 py-24">
      <div className="mx-auto max-w-6xl">
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mx-auto max-w-2xl text-center"
        >
          <h2 className="font-serif text-4xl font-medium tracking-tight text-neutral-900 md:text-5xl">
            Why schools choose <em className="pr-1 font-light italic text-neutral-500">Timetablz.</em>
          </h2>
          <p className="mt-5 text-[15px] leading-relaxed text-neutral-500">
            One connected workflow replaces weeks of spreadsheet redrafts. Set up your school, describe your
            rules in plain English, and get a clash-free timetable for every section and every teacher.
          </p>
          <a
            href="?page=why"
            className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-neutral-900 hover:text-neutral-600"
          >
            Why Timetablz
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </a>
        </motion.div>

        <div className="mt-16 grid items-center gap-12 lg:grid-cols-[1fr_minmax(0,460px)_1fr] lg:gap-10">
          <div className="order-1 lg:hidden">
            <WhyMockup />
          </div>
          <div className="order-2 grid gap-10 sm:grid-cols-2 lg:order-none lg:grid-cols-1 lg:justify-items-end lg:gap-14">
            {WHY_BENEFITS.left.map((b, i) => (
              <WhyBenefit key={b.title} {...b} delay={0.1 * i} />
            ))}
          </div>
          <div className="hidden lg:block">
            <WhyMockup />
          </div>
          <div className="order-3 grid gap-10 sm:grid-cols-2 lg:order-none lg:grid-cols-1 lg:gap-14">
            {WHY_BENEFITS.right.map((b, i) => (
              <WhyBenefit key={b.title} {...b} delay={0.1 * i + 0.1} />
            ))}
          </div>
        </div>
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


/**
 * The last thing before the footer: one big line and two ways in, in its own
 * band so it reads as the page's closing ask rather than more footer.
 * "Book a demo" goes to the Contact page until there's a booking link.
 */
function ClosingCta({ onGetStarted, signedIn }) {
  return (
    <section className="border-t border-neutral-200 bg-white">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.4 }}
        transition={{ duration: 0.5 }}
        className="mx-auto max-w-6xl px-6 py-24 md:py-28"
      >
        <h2 className="max-w-4xl font-serif text-4xl font-medium leading-[1.1] tracking-tight text-neutral-900 md:text-6xl">
          Make the hardest timetable feel effortless, with Timetablz<span className="text-emerald-600">.</span>
        </h2>
        <div className="mt-10 flex flex-wrap items-center gap-4">
          <a
            href="?page=contact"
            className="rounded-lg bg-neutral-900 px-7 py-3.5 text-[15px] font-semibold text-white hover:bg-neutral-700"
          >
            Book a demo
          </a>
          <button
            onClick={onGetStarted}
            className="rounded-lg border border-neutral-900 px-7 py-3.5 text-[15px] font-semibold text-neutral-900 hover:bg-neutral-100"
          >
            {signedIn ? 'Open app' : 'Get started free'}
          </button>
        </div>
      </motion.div>
    </section>
  )
}

