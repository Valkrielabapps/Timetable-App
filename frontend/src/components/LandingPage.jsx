import { motion, useReducedMotion } from 'framer-motion'
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
    // One typeface for the whole homepage - Inter, the font of the numbers
    // section - headings included.
    <div className="min-h-screen bg-white text-neutral-900" style={{ fontFamily: 'var(--font-display)' }}>
      <LandingNav onGetStarted={onGetStarted} onSignIn={onSignIn} signedIn={signedIn} />
      <Hero onGetStarted={onGetStarted} signedIn={signedIn} />
      <WorkflowDemo />
      <MetricsSection />
      <WhyChoose onGetStarted={onGetStarted} />
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
          {/* The heading's words are real text (sr-only) rather than an
              aria-label, so search engines read "Instant timetables for
              schools and colleges" as the page's H1; the animated version
              beside it is for sighted visitors only. */}
          <h1 className="text-5xl font-medium leading-[1.05] tracking-tight text-white md:text-6xl">
            <span className="sr-only">Instant timetables for schools and colleges</span>
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
            href="/customers"
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

/**
 * The product demo: an 18-second silent video of the real workflow (set up
 * sections, write a rule in plain English, generate, drag a lesson and see
 * what fits), looping like an ad. Made with made-up school data by
 * marketing/homepage-video/render.py; the files live in public/media/.
 *
 * muted + playsInline are what let browsers autoplay it, phones included.
 * Someone who has asked for reduced motion gets the still poster with the
 * controls, so it plays only if they choose to.
 */
function WorkflowDemo() {
  const reduceMotion = useReducedMotion()
  return (
    // The same near-black as the video's own background (#090909), so the
    // video has no visible edge and reads as part of the page.
    <section id="features" style={{ backgroundColor: '#090909' }}>
      <div className="mx-auto max-w-[1600px] px-2 pb-10 pt-8 sm:px-6">
      <div>
        <video
          className="block aspect-video w-full"
          autoPlay={!reduceMotion}
          controls={reduceMotion}
          muted
          loop
          playsInline
          preload="metadata"
          poster="/media/timetablz-demo-poster.jpg"
          aria-label="Timetablz in 18 seconds: set up a school, write a rule, generate a clash-free timetable and drag a lesson to adjust it"
        >
          <source src="/media/timetablz-demo.webm" type="video/webm" />
          <source src="/media/timetablz-demo.mp4" type="video/mp4" />
        </video>
      </div>
      </div>
    </section>
  )
}

// The headline of the numbers section. Replace with a school's confirmed
// figures when there are some, e.g. before: 'From 3 weeks of work by hand.',
// after: '10 minutes'.
const TIME_SAVED = {
  before: 'A timetable that takes weeks by hand.',
  after: 'Minutes.',
}

// Real numbers so far, across every school using Timetablz. Update them as
// schools join - they are the claim, so they have to stay true.
const CAPABILITY_STATS = [
  { n: '01', label: 'Schools', value: '1', unit: 'school', note: 'Running its whole timetable on Timetablz' },
  { n: '02', label: 'Students', value: '500+', unit: 'students', note: 'On clash-free timetables every week' },
  { n: '03', label: 'Teachers', value: '50+', unit: 'teachers', note: 'Scheduled with no double-booking' },
  { n: '04', label: 'Clashes', value: '0', unit: 'clashes', note: 'Teacher and room, in every timetable' },
]

/**
 * The numbers, laid out like Papermark's: a one-line claim, one very large
 * light number, a thin rule, then four columns - index, name, a big light
 * figure with its unit beside it, and a line of detail. Inter at weight 300
 * for the figures; everything else stays in the site's own font.
 */
function MetricsSection() {
  return (
    <section className="border-t border-neutral-100 bg-white px-6 py-24">
      <div className="mx-auto max-w-7xl">
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
        >
          <p className="text-xl text-neutral-900 md:text-2xl">{TIME_SAVED.before}</p>
          <p
            className="mt-2 font-light leading-none tracking-[-0.04em] text-neutral-950 tabular-nums"
            style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(4.5rem, 13vw, 11rem)' }}
          >
            {TIME_SAVED.after}
          </p>
        </motion.div>

        <div className="mt-16 flex flex-wrap items-baseline justify-between gap-2 border-b border-neutral-200 pb-5">
          <p className="text-[13px] uppercase tracking-[0.08em] text-neutral-500">
            500+ students and 50+ teachers already on Timetablz
          </p>
          <p className="text-[13px] text-neutral-500">Live schools · 2026</p>
        </div>

        <div className="divide-y divide-neutral-200 lg:grid lg:grid-cols-4 lg:divide-x lg:divide-y-0">
          {CAPABILITY_STATS.map((stat, i) => (
            <motion.div
              key={stat.n}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, amount: 0.3 }}
              variants={fadeUp}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              className="py-8 lg:px-9 lg:py-10 lg:first:pl-0"
            >
              <p className="text-[13px] text-neutral-400 tabular-nums">{stat.n}</p>
              <p className="mt-8 text-[15px] font-semibold uppercase tracking-[0.12em] text-neutral-900">{stat.label}</p>
              <p className="mt-10 flex items-baseline gap-2.5">
                <span
                  className="font-light leading-none tracking-[-0.04em] text-neutral-950 tabular-nums"
                  style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(3.25rem, 5vw, 4.5rem)' }}
                >
                  {stat.value}
                </span>
                <span className="text-lg text-neutral-500" style={{ fontFamily: 'var(--font-display)' }}>
                  {stat.unit}
                </span>
              </p>
              <p className="mt-6 text-[15px] leading-relaxed text-neutral-500">{stat.note}</p>
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
 * "Why schools choose Timetablz", laid out like Deel's hero: a black panel
 * on the left with the claim, a pick-what-you-need grid and the call to
 * action; a photo on the right with the product floating over it as small
 * cards. Black and white throughout - green only on the "generated" tick,
 * the one place it means something.
 *
 * The photo is /media/why-person.jpg (frontend/public/media), an
 * AI-generated person, shown in black and white. Until that file exists the
 * panel shows a plain dark gradient behind the cards, so nothing looks
 * broken.
 */
const WHY_OPTIONS = [
  'Build the whole timetable',
  'Handle electives',
  'Cover absent teachers',
  'Keep approved grades fixed',
  'Export to Excel & PDF',
]

function WhyCard({ className = '', delay = 0, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.45, delay }}
      className={`absolute rounded-2xl bg-white shadow-[0_18px_50px_-18px_rgba(0,0,0,0.45)] ${className}`}
    >
      {children}
    </motion.div>
  )
}

function WhyChoose({ onGetStarted }) {
  const [picked, setPicked] = useState(() => new Set([WHY_OPTIONS[0]]))
  const [photo, setPhoto] = useState(true)
  const toggle = (o) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(o)) next.delete(o)
      else next.add(o)
      return next
    })

  return (
    <section className="bg-white px-3 py-6 sm:px-5">
      <div className="mx-auto grid max-w-[1600px] gap-3 lg:grid-cols-2">
        {/* Left: the claim, what you need, start */}
        <div className="flex flex-col justify-center rounded-3xl bg-neutral-950 px-8 py-14 text-white sm:px-14 lg:min-h-[640px] lg:px-20">
          <motion.h2
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.4 }}
            variants={fadeUp}
            transition={{ duration: 0.5 }}
            className="max-w-xl text-5xl font-semibold leading-[1.02] tracking-[-0.03em] md:text-6xl"
          >
            Build, adjust and share every timetable in your school.
          </motion.h2>

          <p className="mt-12 text-lg font-medium">What would you like to do with Timetablz?</p>
          <div className="mt-4 grid max-w-xl grid-cols-2 gap-2.5 sm:grid-cols-3">
            {WHY_OPTIONS.map((o) => {
              const on = picked.has(o)
              return (
                <button
                  key={o}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(o)}
                  className={`flex min-h-[92px] flex-col items-center justify-center gap-2.5 rounded-xl border px-3 py-4 text-center text-[14px] font-medium leading-tight transition-colors ${
                    on ? 'border-white bg-white text-neutral-950' : 'border-white/20 text-white hover:border-white/50'
                  }`}
                >
                  <span
                    className={`flex h-4 w-4 items-center justify-center rounded border ${
                      on ? 'border-neutral-950 bg-neutral-950' : 'border-white/60'
                    }`}
                    aria-hidden="true"
                  >
                    {on && (
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    )}
                  </span>
                  {o}
                </button>
              )
            })}
          </div>

          <button
            type="button"
            onClick={onGetStarted}
            className="mt-8 w-full max-w-xl rounded-full bg-white px-6 py-4 text-base font-semibold text-neutral-950 transition-colors hover:bg-neutral-200"
          >
            Start free
          </button>
          <p className="mt-4 max-w-xl text-center text-sm text-white/55">14 days free · No card needed</p>
        </div>

        {/* Right: a person, with the product floating over the photo */}
        <div className="relative min-h-[560px] overflow-hidden rounded-3xl bg-gradient-to-br from-neutral-800 to-neutral-950 lg:min-h-[640px]">
          {photo && (
            <img
              src="/media/why-person.jpg"
              alt=""
              onError={() => setPhoto(false)}
              className="absolute inset-0 h-full w-full object-cover grayscale"
              loading="lazy"
            />
          )}

          <WhyCard className="left-6 top-6 w-[min(300px,calc(100%-3rem))] p-5 sm:left-8 sm:top-8">
            <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
              <span className="text-[12px] font-semibold uppercase tracking-[0.1em] text-neutral-500">Timetable generated</span>
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              </span>
            </div>
            <p className="mt-3 text-[44px] font-light leading-none tracking-[-0.04em] text-neutral-950 tabular-nums">0 clashes</p>
            <p className="mt-2 text-[13px] text-neutral-500">18 sections · 32 teachers</p>
          </WhyCard>

          {[
            ['Electives', 'left-6 top-[218px] sm:left-8', 0.1],
            ['Lab double periods', 'left-6 top-[278px] sm:left-24', 0.18],
            ['Substitutes', 'left-6 top-[338px] sm:left-14', 0.26],
          ].map(([label, pos, delay]) => (
            <WhyCard key={label} className={`${pos} flex items-center gap-2.5 px-4 py-2.5`} delay={delay}>
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-neutral-950">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              </span>
              <span className="text-[14px] font-medium text-neutral-900">{label}</span>
            </WhyCard>
          ))}

          <WhyCard className="right-6 top-[150px] hidden px-4 py-3 sm:block sm:right-8" delay={0.2}>
            <p className="text-[12px] text-neutral-500">Physics Lab · Grade 11 A</p>
            <p className="mt-0.5 text-[15px] font-semibold text-neutral-950">Double period, Tue P3–P4</p>
            <span className="mt-2 inline-block rounded-full border border-neutral-950 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-neutral-950">
              Rule followed
            </span>
          </WhyCard>

          <WhyCard className="bottom-6 right-6 w-[min(300px,calc(100%-3rem))] px-5 py-4 sm:bottom-8 sm:right-8" delay={0.3}>
            <p className="text-[12px] font-semibold uppercase tracking-[0.1em] text-neutral-500">Rules in plain English</p>
            <p className="mt-2 text-[17px] font-medium leading-snug text-neutral-950">&ldquo;No PE right after lunch.&rdquo;</p>
            <p className="mt-1 text-[13px] text-neutral-500">Read, checked and applied to every section</p>
          </WhyCard>
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
          className="mb-10 text-3xl font-medium tracking-tight text-white md:text-4xl"
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
        <h2 className="max-w-4xl text-4xl font-medium leading-[1.1] tracking-tight text-neutral-900 md:text-6xl">
          Make the hardest timetable feel effortless, with Timetablz<span className="text-emerald-600">.</span>
        </h2>
        <div className="mt-10 flex flex-wrap items-center gap-4">
          <a
            href="/contact"
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

