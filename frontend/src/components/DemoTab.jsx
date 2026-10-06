/**
 * Demo page, opened from the sidebar. Shows a walkthrough video once one
 * exists. Until then it shows a placeholder, so the sidebar link can ship
 * before the video does.
 *
 * To add the video, set DEMO_VIDEO_URL below to one of:
 *   - a YouTube / Loom / Vimeo *embed* link
 *       https://www.youtube.com/embed/VIDEO_ID
 *       https://www.loom.com/embed/VIDEO_ID
 *   - a direct file link ending in .mp4 or .webm
 * and optionally fill in DEMO_TITLE / DEMO_DESCRIPTION.
 */
const DEMO_VIDEO_URL = ''
const DEMO_TITLE = 'See Timetablz in action'
const DEMO_DESCRIPTION = 'A short walkthrough: add your teachers and subjects, type your rules, and generate a clash-free timetable.'

const isFile = (url) => /\.(mp4|webm|ogg)(\?.*)?$/i.test(url)

export default function DemoTab() {
  return (
    <div className="flex max-w-4xl flex-col gap-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Demo</h2>
        <p className="mt-1 text-sm text-slate-500">{DEMO_DESCRIPTION}</p>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        {DEMO_VIDEO_URL ? (
          <div className="aspect-video w-full bg-black">
            {isFile(DEMO_VIDEO_URL) ? (
              <video src={DEMO_VIDEO_URL} title={DEMO_TITLE} controls preload="metadata" className="h-full w-full" />
            ) : (
              <iframe
                src={DEMO_VIDEO_URL}
                title={DEMO_TITLE}
                className="h-full w-full"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                allowFullScreen
              />
            )}
          </div>
        ) : (
          <div className="flex aspect-video w-full flex-col items-center justify-center gap-3 bg-slate-50 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-500">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" />
              </svg>
            </span>
            <div>
              <p className="text-sm font-medium text-slate-700">Demo video coming soon</p>
              <p className="mt-1 text-xs text-slate-500">We're recording a walkthrough. Check back shortly.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
