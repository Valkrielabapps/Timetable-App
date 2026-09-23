import { motion } from 'framer-motion'
import shishyaPublicSchoolPhoto from '../assets/shishya-public-school.png'
import shishyaPublicSchoolGatePhoto from '../assets/shishya-public-school-gate.png'
import shishyaPublicSchoolEntrancePhoto from '../assets/shishya-public-school-entrance.png'

/**
 * Standalone Customers page — reached via `?page=customers` (same
 * no-router pattern as AboutPage/SupportPage; see App.jsx). Same dark
 * theme and wide two-column section layout as those two pages.
 *
 * The nav and footer's "Customers" link used to jump to the `#customers`
 * anchor on the homepage (Testimonials, LandingPage.jsx) — it now points
 * here instead, for a dedicated page with more room to be honest about
 * where things actually stand.
 *
 * Timetablz has exactly one real customer as of writing this: Shishya
 * Public School, Dehradun (see TrustBar/Testimonials in LandingPage.jsx
 * for the same standard applied there). This page does not pad that out
 * into a "customers" grid implying more than one, and does not invent a
 * quote attributed to the school, same reasoning as
 * TESTIMONIAL_TILE_STYLES in LandingPage.jsx: a fabricated quote paired
 * with a real, identifiable school reads as putting words in their
 * mouth. What's here is a fuller, honest look at the one real
 * relationship that exists, not a wider one that doesn't.
 */

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

const PHOTOS = [
  { image: shishyaPublicSchoolGatePhoto, caption: 'Campus gate' },
  { image: shishyaPublicSchoolEntrancePhoto, caption: 'Main building' },
  { image: shishyaPublicSchoolPhoto, caption: 'Front of school' },
]

export default function CustomersPage({ onBack, onGetStarted }) {
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
          <p className="text-xs font-medium uppercase tracking-widest text-neutral-500">Customers</p>
          <h1 className="mt-3 font-serif text-5xl font-medium leading-tight tracking-tight text-white md:text-6xl">
            Who's using Timetablz
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-neutral-400">
            We're early, and we'd rather show you the one real school we work with today than pad this page
            out with names that aren't real yet.
          </p>
        </motion.div>

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={fadeUp}
          transition={{ duration: 0.5 }}
          className="mt-20 grid gap-4 sm:grid-cols-3"
        >
          {PHOTOS.map((p) => (
            <div key={p.caption} className="overflow-hidden rounded-xl border border-white/10">
              <img src={p.image} alt={`${p.caption}, Shishya Public School, Dehradun`} className="h-56 w-full object-cover" />
              <p className="px-4 py-3 text-sm text-neutral-400">{p.caption}</p>
            </div>
          ))}
        </motion.div>

        <div className="mt-20 divide-y divide-white/10 border-t border-white/10">
          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.3 }}
            variants={fadeUp}
            transition={{ duration: 0.5 }}
            className="grid gap-4 py-14 md:grid-cols-[280px_1fr] md:gap-12"
          >
            <h2 className="font-serif text-3xl font-medium text-white">
              Shishya Public
              <br />
              School, Dehradun
            </h2>
            <div className="max-w-2xl space-y-4 text-[15px] leading-relaxed text-neutral-400">
              <p>
                Our first real school partner. We're building Timetablz alongside them rather than for them,
                which means their timetabling needs are shaping what gets prioritized rather than a guess at
                what schools in general might want.
              </p>
              <p>
                We won't put words in their mouth with a manufactured quote, so instead of a testimonial,
                here's the honest version: they're one of the first schools actually using Timetablz to build
                a real timetable, and that relationship is still early.
              </p>
            </div>
          </motion.div>

          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.3 }}
            variants={fadeUp}
            transition={{ duration: 0.5 }}
            className="grid gap-4 py-14 md:grid-cols-[280px_1fr] md:gap-12"
          >
            <h2 className="font-serif text-3xl font-medium text-white">Want to be next</h2>
            <div className="max-w-2xl text-[15px] leading-relaxed text-neutral-400">
              <p>
                If you run a school or college and manual timetabling is eating a week of someone's term
                every term, we'd like to work with you directly while the product is still early: your
                feedback carries real weight right now in a way it won't once there are hundreds of schools
                on the platform.
              </p>
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
          <p className="text-lg font-medium text-white">Ready to try it on your own school?</p>
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
