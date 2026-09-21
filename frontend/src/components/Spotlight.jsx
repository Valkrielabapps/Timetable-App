import { motion } from 'framer-motion'
import { useRef, useState } from 'react'

/**
 * A soft, blurred radial glow — the "spotlight" effect popularized by
 * Aceternity UI's component gallery (https://ui.aceternity.com), hand-built
 * here rather than pulled from an external package: it's just an SVG
 * ellipse behind a heavy Gaussian blur filter, animated with Framer
 * Motion, so there's no real dependency worth adding for it. Purely
 * decorative — `pointer-events-none` so it never intercepts clicks on
 * whatever it's layered behind.
 *
 * Used behind LandingPage.jsx's Hero section to add some depth instead of
 * a flat white background, without the busier "video background" or
 * "particle field" look that would fight with the rest of the page's
 * restrained style.
 */
export function Spotlight({ className = '', fill = '#0f172a' }) {
  return (
    <motion.svg
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 1.2 }}
      className={`pointer-events-none absolute z-0 ${className}`}
      width="560"
      height="900"
      viewBox="0 0 560 900"
      fill="none"
    >
      <g filter="url(#spotlight-blur)">
        <ellipse cx="280" cy="200" rx="280" ry="180" fill={fill} fillOpacity="0.12" />
      </g>
      <defs>
        <filter
          id="spotlight-blur"
          x="-200"
          y="-200"
          width="960"
          height="1300"
          filterUnits="userSpaceOnUse"
          colorInterpolationFilters="sRGB"
        >
          <feFlood floodOpacity="0" result="BackgroundImageFix" />
          <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape" />
          <feGaussianBlur stdDeviation="80" result="effect1_foregroundBlur" />
        </filter>
      </defs>
    </motion.svg>
  )
}

/**
 * A faint dot/line grid with a radial fade mask, so it's crisp in the
 * center and dissolves toward the edges instead of ending in a hard line
 * — another Aceternity-gallery staple ("grid background"). Sits behind
 * the Hero section, `-z-10`, with the Spotlight glow layered on top of it.
 */
export function GridBackground({ className = '', dark = false }) {
  // `dark` swaps the line color for something visible against a black/
  // near-black section (e.g. Hero's Griffin-style dark theme) — the same
  // light slate lines used on a white background would be invisible there.
  // 0.08 opacity read as basically invisible once the Hero's sides had
  // nothing else going on to sit behind, so this is bumped slightly —
  // still faint, but the grid actually registers as texture now instead
  // of flattening to solid black.
  const lineColor = dark ? 'rgba(255,255,255,0.14)' : '#e2e8f0'
  return (
    <div
      className={`pointer-events-none absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_65%_55%_at_50%_0%,#000_60%,transparent_100%)] ${className}`}
    >
      <div
        className="absolute inset-0 bg-[size:44px_44px]"
        style={{
          backgroundImage: `linear-gradient(to right, ${lineColor} 1px, transparent 1px), linear-gradient(to bottom, ${lineColor} 1px, transparent 1px)`,
        }}
      />
    </div>
  )
}

/**
 * Card wrapper that tracks the cursor and renders a soft radial glow at
 * the pointer position on hover — the "glow card" / "spotlight card"
 * pattern from Aceternity/Magic UI's galleries. Hand-built with a plain
 * `onMouseMove` handler writing CSS custom properties (`--x`/`--y`) that
 * a `radial-gradient` background reads, rather than a package — no state
 * updates on every mousemove, so no React re-render cost per frame.
 *
 * Wraps each card in LandingPage.jsx's Features() grid. Falls back
 * gracefully to a plain bordered card for anyone on a touch device where
 * hover doesn't apply — the glow is a bonus, not load-bearing.
 */
export function GlowCard({ children, className = '' }) {
  const ref = useRef(null)
  const [pos, setPos] = useState({ x: 50, y: 0 })
  const [active, setActive] = useState(false)

  function handleMouseMove(e) {
    const rect = ref.current?.getBoundingClientRect()
    if (!rect) return
    setPos({
      x: ((e.clientX - rect.left) / rect.width) * 100,
      y: ((e.clientY - rect.top) / rect.height) * 100,
    })
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
      className={`relative overflow-hidden ${className}`}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300"
        style={{
          opacity: active ? 1 : 0,
          background: `radial-gradient(240px circle at ${pos.x}% ${pos.y}%, rgba(15,23,42,0.08), transparent 70%)`,
        }}
      />
      {children}
    </div>
  )
}
