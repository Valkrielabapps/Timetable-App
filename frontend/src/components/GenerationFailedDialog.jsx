import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

/**
 * Why the last generation found no timetable, as a dialog rather than a
 * block on the page.
 *
 * `explanation` is the plain-language summary written at failure time (see
 * backend/app/services/infeasibility_explainer.py; null without an API key).
 * `message` is the solver's own diagnosis, one cause per line (see
 * _diagnose_infeasibility in backend/app/services/solver.py) - each shown as
 * its own numbered reason.
 */
export default function GenerationFailedDialog({ open, explanation, message, onClose, onOpenConstraints }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const reasons = (message || 'Generation failed for an unknown reason.').split('\n').map((l) => l.trim()).filter(Boolean)

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 sm:p-8">
          <motion.div
            className="absolute inset-0 bg-neutral-900/45"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onMouseDown={onClose}
            aria-hidden="true"
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="generation-failed-title"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="relative flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
          >
            <div className="flex items-start gap-4 border-b border-slate-100 px-7 pb-5 pt-7">
              <div className="flex h-11 w-11 flex-none items-center justify-center rounded-full bg-red-50 text-red-600">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 8v4" />
                  <path d="M12 16h.01" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <h2 id="generation-failed-title" className="text-xl font-semibold tracking-tight text-neutral-900">
                  We couldn&rsquo;t build a conflict-free timetable
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Nothing was changed. Fix the {reasons.length === 1 ? 'issue' : 'issues'} below and generate again.
                </p>
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="-mr-2 -mt-1 rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-7 py-6">
              {explanation && (
                <section className="mb-6">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">What&rsquo;s wrong</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-slate-700">{explanation}</p>
                </section>
              )}
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {reasons.length === 1 ? 'Reason' : `Reasons (${reasons.length})`}
                </h3>
                <ol className="mt-3 flex flex-col gap-2.5">
                  {reasons.map((reason, i) => (
                    <li key={i} className="flex gap-3 rounded-lg border border-slate-200 bg-slate-50/60 px-4 py-3">
                      <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-neutral-900 text-xs font-semibold text-white">
                        {i + 1}
                      </span>
                      <span className="text-sm leading-relaxed text-slate-700">{reason}</span>
                    </li>
                  ))}
                </ol>
              </section>
            </div>

            <div className="flex justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-7 py-4">
              {onOpenConstraints && (
                <button
                  onClick={() => {
                    onClose()
                    onOpenConstraints()
                  }}
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Review constraints
                </button>
              )}
              <button onClick={onClose} className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700">
                Got it
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
