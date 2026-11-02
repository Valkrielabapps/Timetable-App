import { useState } from 'react'
import SendToSupport from './SendToSupport'

/**
 * The setup check above Generate (backend/app/services/setup_check.py):
 * problems that will stop a timetable, found in a second without running the
 * solver, each with a Fix button that opens the section, teacher, block,
 * rule, rooms or periods to change.
 *
 * Errors mean generating will fail until they're fixed; warnings mean it
 * works but something will be missing (a lesson with no teacher or room).
 * Fetched fresh every time the Timetable page opens, since what it checks is
 * edited on the other pages (useSetupCheck in hooks/useSchoolData).
 */
const SHOWN = 5

export default function SetupCheckPanel({ check, loading, onFix, readOnly = false, schoolId = null }) {
  const [showAll, setShowAll] = useState(false)
  if (loading) {
    return <p className="text-xs text-slate-400">Checking the setup…</p>
  }
  if (!check) return null
  const { errors = [], warnings = [] } = check
  if (errors.length === 0 && warnings.length === 0) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-emerald-700">
        <span aria-hidden="true">✓</span> Setup check: nothing found that would stop a timetable.
      </p>
    )
  }
  const items = [...errors, ...warnings]
  const shown = showAll ? items : items.slice(0, SHOWN)
  return (
    <section
      aria-label="Setup check"
      className={`rounded-md border px-3 py-2.5 text-sm ${errors.length ? 'border-red-200 bg-red-50' : 'border-amber-200 bg-amber-50'}`}
    >
      <p className={`font-medium ${errors.length ? 'text-red-900' : 'text-amber-900'}`}>
        {errors.length > 0
          ? `${errors.length === 1 ? '1 problem' : `${errors.length} problems`} will stop the timetable from generating`
          : `${warnings.length === 1 ? '1 thing' : `${warnings.length} things`} to look at before generating`}
        {errors.length > 0 && warnings.length > 0 && (
          <span className="font-normal text-red-800"> · and {warnings.length} to look at</span>
        )}
      </p>
      <ul className="mt-2 flex flex-col gap-2">
        {shown.map((issue, i) => (
          <li key={`${issue.kind}-${i}`} className="flex items-start justify-between gap-3">
            <span className="flex items-start gap-2">
              <span
                className={`mt-1.5 h-2 w-2 flex-none rounded-full ${issue.severity === 'error' ? 'bg-red-600' : 'bg-amber-500'}`}
                aria-label={issue.severity === 'error' ? 'Will stop generation' : 'Worth a look'}
              />
              <span className={issue.severity === 'error' ? 'text-red-900' : 'text-amber-900'}>{issue.message}</span>
            </span>
            {issue.fix && onFix && (
              <button
                type="button"
                onClick={() => onFix(issue.fix)}
                className="flex-none rounded border border-slate-300 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                title={issue.fix.label}
              >
                {readOnly ? 'Show' : 'Fix'}
              </button>
            )}
          </li>
        ))}
      </ul>
      {errors.length > 0 && (
        <div className="mt-2">
          <SendToSupport
            schoolId={schoolId}
            compact
            context={{ where: 'the setup check', reasons: errors.map((e) => e.message) }}
          />
        </div>
      )}
      {items.length > SHOWN && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-2 text-xs font-medium text-slate-700 underline"
        >
          {showAll ? 'Show fewer' : `Show all ${items.length}`}
        </button>
      )}
    </section>
  )
}
