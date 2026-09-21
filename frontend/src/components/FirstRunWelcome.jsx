import { useState } from 'react'
import BulkAddClassGroups from './BulkAddClassGroups'

/**
 * Shown instead of the tab area when a school has zero grades/sections yet
 * (App.jsx: `selectedSchool && !selectedClassGroup`). This exists because
 * every other tab (Overview, Data Entry, Constraints, Timetable) needs a
 * selected class group to render anything meaningful — Data Entry's
 * "requirements" list, Overview's checklist, and Timetable's grid are all
 * scoped to one section — so a school with no sections at all previously
 * just saw a tiny "Add a grade/section to get started" hint buried in the
 * header, with no explanation of what happens after that, or why a
 * section has to exist before periods/subjects/teachers (which are
 * actually school-wide, not per-section) can be entered.
 *
 * Defaults straight to the bulk/range form (most schools have several
 * grades, not one), with plain from/to + section-chip controls instead of
 * raw range syntax — see BulkAddClassGroups.jsx. Adding a single section
 * is still available but tucked behind a small link rather than a
 * co-equal toggle, since it's the less common first action. Once at least
 * one section is added, App.jsx selects one automatically and
 * OverviewTab's checklist takes over guiding the rest of the setup.
 */
export default function FirstRunWelcome({ schoolName, institutionType, onAddClassGroup, onAddClassGroups }) {
  const [singleMode, setSingleMode] = useState(false)
  const [grade, setGrade] = useState('')
  const [section, setSection] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!grade.trim() || !section.trim()) return
    setSubmitting(true)
    try {
      await onAddClassGroup(grade.trim(), section.trim())
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Welcome to {schoolName}</h2>
        <p className="mt-1.5 text-sm text-slate-500">
          Let's start with your grades and sections. After this, you'll add subjects and
          teachers, then build the timetable.
        </p>
      </div>

      {!singleMode ? (
        <>
          <BulkAddClassGroups onAddClassGroups={onAddClassGroups} institutionType={institutionType} />
          <button
            type="button"
            onClick={() => setSingleMode(true)}
            className="w-fit text-xs font-medium text-slate-400 hover:text-slate-600 hover:underline"
          >
            Just adding one section? Do that instead
          </button>
        </>
      ) : (
        <>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-lg border border-slate-200 p-5">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">Grade / Year</label>
              <input
                value={grade}
                onChange={(e) => setGrade(e.target.value)}
                placeholder={institutionType === 'college' ? 'Semester 3' : 'Grade 8'}
                autoFocus
                className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">Section / Division</label>
              <input
                value={section}
                onChange={(e) => setSection(e.target.value)}
                placeholder="A, or Div B"
                className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
              />
            </div>
            <button
              disabled={submitting || !grade.trim() || !section.trim()}
              className="mt-1 w-fit rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {submitting ? 'Adding…' : 'Add section and continue'}
            </button>
          </form>
          <button
            type="button"
            onClick={() => setSingleMode(false)}
            className="w-fit text-xs font-medium text-slate-400 hover:text-slate-600 hover:underline"
          >
            Back to adding multiple grades at once
          </button>
        </>
      )}
    </div>
  )
}
