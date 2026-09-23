import { useEffect, useRef, useState } from 'react'

/**
 * Standalone "Why Timetablz" page — reached via `?page=why` (same
 * no-router pattern as PricingPage/SupportPage; see App.jsx). The nav's
 * "Why Timetablz" link used to jump to the `#features` anchor (the
 * WorkflowDemo section); it now navigates here instead, by request.
 *
 * Layout is modeled on Griffin's product page (griffin.com) — a dark,
 * two-column "scrollytelling" section: a numbered step list on the left
 * that the visitor scrolls through, and a sticky isometric diagram on the
 * right whose highlighted layer updates to match whichever step is
 * currently in view (tracked via IntersectionObserver on each step's
 * section below, not a scroll-position calculation — more resilient to
 * different viewport heights).
 *
 * The four steps are the same STEPS content LandingPage.jsx's HowItWorks
 * section used before it was removed from the homepage (see that file) —
 * reused verbatim rather than inventing new copy, since it already
 * accurately describes the real four-stage workflow (Data Entry →
 * Constraints → Solver → Timetable, the same stage names WorkflowDemo's
 * sidebar uses on the homepage).
 */

const STEPS = [
  {
    n: '01',
    title: 'Set up your school',
    body: 'Periods, subjects, teachers, and sections: type them in or bulk-import a spreadsheet.',
    layer: 'Data Entry',
  },
  {
    n: '02',
    title: 'Describe your rules',
    body: 'Plain-English constraints, scoped to a subject, teacher, day, or specific section.',
    layer: 'Constraints',
  },
  {
    n: '03',
    title: 'Generate',
    body: "The solver builds every section's schedule at once, with zero teacher or room clashes.",
    layer: 'Solver',
  },
  {
    n: '04',
    title: 'Fine-tune and export',
    body: 'Lock slots, drag to adjust, then export to Excel or PDF for the staff room wall.',
    layer: 'Timetable',
  },
]

const LAYER_LABELS = STEPS.map((s) => s.layer)

/**
 * A stack of four isometric "layer" diamonds — one static diagram whose
 * highlighted layer changes with `activeStep`, echoing how Griffin's own
 * diagram stays on screen while different parts of it light up as you
 * scroll through YOUR APP / YOUR TECH / OUR PLATFORM / OUR BANK LICENSE.
 * Plain SVG, no illustration library — four rhombi are simple enough to
 * hand-draw with polygon points.
 */
function StepVisual({ activeStep }) {
  const gap = 78

  return (
    <svg viewBox="0 0 320 420" className="h-[420px] w-[320px]">
      {/* Faint vertical spine connecting the layers, Griffin-diagram-style. */}
      <line x1="160" y1="40" x2="160" y2="380" stroke="rgba(255,255,255,0.12)" strokeWidth="1" />

      {LAYER_LABELS.map((label, i) => {
        const cy = 70 + i * gap
        const active = i === activeStep
        return (
          <g key={label} transform={`translate(160, ${cy})`}>
            <polygon
              points="-110,0 0,-30 110,0 0,30"
              fill={active ? 'rgba(255,255,255,0.08)' : 'transparent'}
              stroke={active ? '#ffffff' : 'rgba(255,255,255,0.22)'}
              strokeWidth={active ? 1.5 : 1}
              style={{ transition: 'fill 0.4s ease, stroke 0.4s ease, stroke-width 0.4s ease' }}
            />
            <text
              x="0"
              y="5"
              textAnchor="middle"
              fontSize="11"
              letterSpacing="1"
              fill={active ? '#ffffff' : 'rgba(255,255,255,0.35)'}
              style={{ transition: 'fill 0.4s ease' }}
            >
              {label.toUpperCase()}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default function WhyTimetablzPage({ onBack, onGetStarted }) {
  const [activeStep, setActiveStep] = useState(0)
  const stepRefs = useRef([])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveStep(Number(entry.target.dataset.stepIndex))
          }
        })
      },
      // A thin band through the vertical middle of the viewport — a step
      // becomes "active" once it crosses the center, not as soon as any
      // part of it is visible, so the transition lines up with whichever
      // step the visitor is actually reading.
      { rootMargin: '-45% 0px -45% 0px', threshold: 0 }
    )
    stepRefs.current.forEach((el) => el && observer.observe(el))
    return () => observer.disconnect()
  }, [])

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

      <div className="mx-auto max-w-6xl px-6 pb-10 pt-20">
        <h1 className="max-w-2xl font-serif text-4xl font-medium leading-tight tracking-tight md:text-5xl">
          Built to <em className="text-neutral-400">adapt</em> to how your school actually schedules
        </h1>
        <p className="mt-4 max-w-xl text-neutral-400">
          One connected workflow, from a blank slate to a clash-free timetable. Here's what actually
          happens at each step.
        </p>
      </div>

      <div className="relative mx-auto max-w-6xl px-6 pb-32">
        <div className="grid gap-12 lg:grid-cols-2">
          <div className="relative">
            <div className="absolute bottom-0 left-[15px] top-2 w-px bg-white/10" />
            {STEPS.map((s, i) => (
              <div
                key={s.n}
                ref={(el) => (stepRefs.current[i] = el)}
                data-step-index={i}
                className="relative flex min-h-[65vh] flex-col justify-center pl-12"
              >
                <span
                  className={`absolute left-0 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors duration-300 ${
                    activeStep === i ? 'border-white bg-white text-black' : 'border-white/20 text-neutral-500'
                  }`}
                >
                  {s.n}
                </span>
                <p
                  className={`text-xs font-medium uppercase tracking-widest transition-colors duration-300 ${
                    activeStep === i ? 'text-white' : 'text-neutral-600'
                  }`}
                >
                  Step {s.n} · {s.layer}
                </p>
                <h3
                  className={`mt-3 font-serif text-3xl font-medium transition-colors duration-300 md:text-4xl ${
                    activeStep === i ? 'text-white' : 'text-neutral-700'
                  }`}
                >
                  {s.title}
                </h3>
                <p
                  className={`mt-4 max-w-sm text-[15px] leading-relaxed transition-colors duration-300 ${
                    activeStep === i ? 'text-neutral-400' : 'text-neutral-700'
                  }`}
                >
                  {s.body}
                </p>
              </div>
            ))}
          </div>

          <div className="hidden lg:block">
            <div className="sticky top-24 flex h-[70vh] items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-neutral-950/60">
              <StepVisual activeStep={activeStep} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
