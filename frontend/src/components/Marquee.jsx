/**
 * Infinite horizontal scroll of chips/cards - the "marquee" pattern from
 * Magic UI's component gallery (https://magicui.design), hand-built with
 * a plain CSS keyframe (`.animate-marquee` in index.css) rather than
 * pulling in their package, since the whole effect is really just "render
 * the content twice, side by side, and slide the wrapper left by exactly
 * one copy's width, forever." Pauses on hover (`group-hover:paused`) so a
 * visitor can actually read an item instead of chasing it.
 *
 * LandingPage.jsx uses this for a strip of real feature highlights
 * instead of customer logos - there are no real customer logos yet (see
 * LandingPage.jsx's top docstring on placeholder content), and a logo
 * marquee with invented company names would be actively misleading in a
 * way a feature-highlight marquee isn't.
 */
export function Marquee({ items, speed = 28, className = '' }) {
  return (
    <div
      className={`group flex w-full overflow-hidden ${className}`}
      style={{ '--marquee-duration': `${speed}s` }}
    >
      <div className="flex w-max shrink-0 animate-marquee items-center gap-3 pr-3 group-hover:[animation-play-state:paused]">
        {items}
      </div>
      <div
        aria-hidden="true"
        className="flex w-max shrink-0 animate-marquee items-center gap-3 pr-3 group-hover:[animation-play-state:paused]"
      >
        {items}
      </div>
    </div>
  )
}
