import { groupSectionIds } from '../electiveSections'
import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import BulkImportPanel from './BulkImportPanel'
import { confirmDialog } from './confirmDialog'
import { compareNames, loadChoice, matchesSearch, saveChoice } from '../sorting'

const SORTS = [
  ['name', 'Name (A–Z)'],
  ['name-desc', 'Name (Z–A)'],
  ['periods', 'Periods/week (most first)'],
  ['sections', 'Sections taking it (most first)'],
  ['teachers', 'Qualified teachers (most first)'],
  ['teachers-asc', 'Qualified teachers (fewest first)'],
]
const SORT_KEY = 'timetablz.subjects.sort'

/**
 * "What does your school teach" - subject name plus optional advanced
 * fields (room type, and for colleges, credits/lab batches). Deliberately
 * does not show periods/week or teacher assignment: those are two other
 * questions ("how much of it does this section need" and "who teaches
 * it"), answered on the Plan and Teachers pages respectively. Splitting
 * them out means this page only ever asks "what subjects exist," instead
 * of a single row doing five unrelated things at once (see DataEntryTab's
 * docstring for the full reasoning behind the three-way split).
 */
export default function SubjectsSection({
  schoolId,
  subjects,
  onSubjectsChanged,
  institutionType,
  readOnly,
  // For the figures each subject is sorted by.
  allRequirements = [],
  teachers = [],
  electiveBlocks = [],
  // To give the teachers ticked when adding a subject that subject too.
  onTeachersChanged = null,
}) {
  const [error, setError] = useState(null)
  const [addSubjectOpen, setAddSubjectOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [sort, setSortState] = useState(() => loadChoice(SORT_KEY, 'name'))
  const setSort = (value) => {
    setSortState(value)
    saveChoice(SORT_KEY, value)
  }
  // Subjects added on this visit stay at the bottom, where "+ Add subject"
  // put them, rather than jumping away mid-edit as their name is typed -
  // "New subject" would otherwise sort under N. Next visit, they take their
  // place in the order like everything else.
  const presentAtStart = useRef(null)
  if (presentAtStart.current === null) presentAtStart.current = new Set(subjects.map((x) => x.id))
  const [showImport, setShowImport] = useState(true)
  // Which subject rows have their "advanced" fields expanded - collapsed
  // by default since most subjects never set these; a row that already
  // has an advanced field set starts expanded so existing settings are
  // never hidden without a trace.
  const [expandedAdvanced, setExpandedAdvanced] = useState(new Set())

  // Display-only: a stable React key per row. A new subject first appears
  // with a temporary id while it saves, then comes back from the server with
  // its real id. Keyed on the id alone, that swap made React treat it as a
  // different row - the "Saving..." row faded out while the saved one faded
  // in just below it, so the row dipped and slid back up. Here the saved
  // subject inherits the temporary row's key instead, so the same row simply
  // stops saying "Saving...". Nothing about the subject itself, or what's
  // sent to the server, changes.
  const rowKeys = useRef(new Map()) // real subject id -> key of the row it replaced
  const lastRender = useRef({ ids: new Set(), pending: [] })
  {
    const currentIds = new Set(subjects.map((s) => s.id))
    for (const temp of lastRender.current.pending) {
      if (currentIds.has(temp.id)) continue // still saving
      const saved = subjects.find(
        (s) => !s._pending && s.name === temp.name && !lastRender.current.ids.has(s.id) && !rowKeys.current.has(s.id)
      )
      if (saved) rowKeys.current.set(saved.id, rowKeys.current.get(temp.id) ?? temp.id)
    }
  }
  useEffect(() => {
    lastRender.current = { ids: new Set(subjects.map((s) => s.id)), pending: subjects.filter((s) => s._pending) }
  }, [subjects])
  const rowKey = (subject) => rowKeys.current.get(subject.id) ?? subject.id

  // Per subject: periods a week across the school (a block counts its
  // periods once per section), the sections taking it, and who can teach it.
  const stats = new Map()
  const stat = (id) => {
    if (!stats.has(id)) stats.set(id, { periods: 0, sections: new Set(), teachers: 0 })
    return stats.get(id)
  }
  for (const r of allRequirements) {
    const st = stat(r.subject_id)
    st.periods += r.periods_per_week || 0
    st.sections.add(r.class_group_id)
  }
  for (const b of electiveBlocks) {
    for (const o of b.options) {
      const st = stat(o.subject_id)
      st.periods += b.periods_per_week || 0
      for (const id of groupSectionIds(b, o)) st.sections.add(id)
    }
  }
  for (const t of teachers) {
    for (const id of t.qualified_subject_ids || []) stat(id).teachers += 1
  }
  const figures = (subject) => {
    const st = stats.get(subject.id)
    return { periods: st?.periods ?? 0, sections: st?.sections.size ?? 0, teachers: st?.teachers ?? 0 }
  }

  const isFresh = (subject) => !presentAtStart.current.has(subject.id) && !presentAtStart.current.has(rowKey(subject))
  const ordered = subjects
    .filter((x) => !isFresh(x) && matchesSearch(x.name, search))
    .sort((a, b) => {
      const name = compareNames(a.name, b.name)
      const fa = figures(a)
      const fb = figures(b)
      switch (sort) {
        case 'name-desc':
          return -name
        case 'periods':
          return fb.periods - fa.periods || name
        case 'sections':
          return fb.sections - fa.sections || name
        case 'teachers':
          return fb.teachers - fa.teachers || name
        case 'teachers-asc':
          return fa.teachers - fb.teachers || name
        default:
          return name
      }
    })
  const shownSubjects = [...ordered, ...subjects.filter(isFresh)]

  useEffect(() => {
    setExpandedAdvanced((prev) => {
      const withAdvanced = subjects.filter(
        (s) => s.required_room_type || s.credits || (s.lab_batch_count && s.lab_batch_count >= 2)
      )
      if (withAdvanced.every((s) => prev.has(s.id))) return prev
      const next = new Set(prev)
      withAdvanced.forEach((s) => next.add(s.id))
      return next
    })
  }, [subjects])

  function toggleAdvanced(subjectId) {
    setExpandedAdvanced((prev) => {
      const next = new Set(prev)
      if (next.has(subjectId)) next.delete(subjectId)
      else next.add(subjectId)
      return next
    })
  }

  async function handleRemoveSubject(id, name) {
    const ok = await confirmDialog({
      title: `Remove ${name}?`,
      message: 'This also removes its periods/week and teacher qualifications for this subject.',
      confirmLabel: 'Remove',
      danger: true,
    })
    if (!ok) return
    try {
      await onSubjectsChanged.delete(id)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUpdateName(id, name) {
    try {
      await onSubjectsChanged.update(id, { name })
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUpdateRoomType(id, requiredRoomType) {
    try {
      await onSubjectsChanged.update(id, { required_room_type: requiredRoomType || null })
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUpdateCredits(id, value) {
    const n = Number(value)
    try {
      await onSubjectsChanged.update(id, { credits: n > 0 ? n : null })
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUpdateLabBatchCount(id, value) {
    const n = Number(value)
    try {
      await onSubjectsChanged.update(id, { lab_batch_count: n >= 2 ? n : null })
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h4 className="text-base font-medium">Subjects</h4>
          <p className="mt-1 text-sm text-slate-500">What your school teaches. Applies to every section.</p>
        </div>
        {!readOnly && (
          <button
            onClick={() => setAddSubjectOpen(true)}
            className="w-fit rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
          >
            + Add subject
          </button>
        )}
      </div>

      <AnimatePresence>
        {addSubjectOpen && (
          <AddSubjectModal
            subjects={subjects}
            teachers={teachers}
            onClose={() => setAddSubjectOpen(false)}
            onAdd={async ({ name, requiredRoomType, teacherIds }) => {
              const created = await onSubjectsChanged.create({
                school_id: schoolId, name, required_room_type: requiredRoomType || null,
              })
              if (created && onTeachersChanged) {
                for (const t of teachers.filter((x) => teacherIds.includes(x.id))) {
                  await onTeachersChanged.update(t.id, {
                    qualified_subject_ids: [...new Set([...(t.qualified_subject_ids || []), created.id])],
                  })
                }
              }
              setAddSubjectOpen(false)
            }}
          />
        )}
      </AnimatePresence>

      {!readOnly && (
        <div className="rounded-lg border border-neutral-200 bg-neutral-100/40 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h5 className="text-sm font-semibold text-neutral-900">Import subjects</h5>
              <p className="mt-0.5 text-xs text-neutral-700/80">
                Upload a spreadsheet instead of adding subjects one at a time.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowImport((v) => !v)}
              className="flex-none text-xs font-medium text-neutral-700 hover:underline"
            >
              {showImport ? 'Hide' : 'Show'}
            </button>
          </div>
          {showImport && (
            <div className="mt-3">
              <BulkImportPanel schoolId={schoolId} resource="subjects" onImported={onSubjectsChanged.reload} />
            </div>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      {subjects.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            aria-label="Search subjects"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search subjects"
            className="w-64 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            Sort by
            <select
              aria-label="Sort subjects"
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-xs text-slate-700"
            >
              {SORTS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-500">
            <th className="py-2 font-medium">Subject</th>
            <th className="w-8 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {/* `initial={false}` skips the enter animation for rows already
              present when this table mounts - without it, every plain tab
              switch back to Subjects replayed a staggered fade-in for the
              *entire* list (DataEntryTab fully remounts on every top-level
              tab switch - see App.jsx's `key={tab}` - so this ran on every
              single visit, not just when a subject was actually added).
              With it, only a genuinely new row (or one being removed)
              animates; everything else just appears, instantly, matching
              the pattern TeachersSection's chips already use. */}
          <AnimatePresence initial={false}>
            {shownSubjects.map((subject) => (
              <motion.tr
                key={rowKey(subject)}
                layout="position"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15, ease: 'easeOut' }}
                className="border-b border-slate-100"
              >
              <td className="py-2 pr-2">
                <label htmlFor={`subject-name-${subject.id}`} className="sr-only">
                  Subject name
                </label>
                <input
                  id={`subject-name-${subject.id}`}
                  defaultValue={subject.name}
                  disabled={readOnly || subject._pending}
                  onBlur={(e) => e.target.value !== subject.name && handleUpdateName(subject.id, e.target.value)}
                  className="w-full max-w-sm rounded px-1.5 py-1 text-sm hover:bg-slate-50 focus:bg-slate-50 focus:outline-none disabled:bg-transparent disabled:text-slate-700"
                />
                {subject._pending && <span className="ml-1.5 text-[11px] text-slate-400">Saving…</span>}
                {!subject._pending && (() => {
                  const f = figures(subject)
                  return (
                    <span className="ml-1.5 text-[11px] text-slate-400">
                      {f.sections} section{f.sections === 1 ? '' : 's'} · {f.periods} periods/week ·{' '}
                      {f.teachers} teacher{f.teachers === 1 ? '' : 's'}
                    </span>
                  )
                })()}
                {subject._pending ? (
                  // Holds the "+ Advanced" line's space while saving, so the
                  // row doesn't grow by a line the moment the save finishes.
                  <button
                    type="button"
                    tabIndex={-1}
                    disabled
                    aria-hidden="true"
                    className="invisible mt-0.5 text-[11px] underline underline-offset-2"
                  >
                    + Advanced (room type
                    {institutionType === 'college' ? ', credits, lab batches' : ''})
                  </button>
                ) : expandedAdvanced.has(subject.id) ? (
                  <>
                    <label htmlFor={`subject-room-type-${subject.id}`} className="sr-only">
                      Required room type (optional)
                    </label>
                    <input
                      id={`subject-room-type-${subject.id}`}
                      defaultValue={subject.required_room_type ?? ''}
                      disabled={readOnly}
                      onBlur={(e) =>
                        e.target.value !== (subject.required_room_type ?? '') &&
                        handleUpdateRoomType(subject.id, e.target.value.trim())
                      }
                      placeholder="Room type (optional, e.g. lab)"
                      title="If set, this subject can only be assigned a room whose type matches exactly"
                      className="mt-0.5 w-full max-w-sm rounded px-1.5 py-0.5 text-xs text-slate-500 placeholder:text-slate-400 hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                    />
                    {institutionType === 'college' && (
                      <div className="mt-0.5 flex items-center gap-2">
                        <label htmlFor={`subject-batches-${subject.id}`} className="text-xs text-slate-400">
                          Split into
                        </label>
                        <input
                          id={`subject-batches-${subject.id}`}
                          type="number"
                          min="0"
                          max="10"
                          defaultValue={subject.lab_batch_count ?? ''}
                          disabled={readOnly}
                          onBlur={(e) =>
                            Number(e.target.value || 0) !== (subject.lab_batch_count ?? 0) &&
                            handleUpdateLabBatchCount(subject.id, e.target.value)
                          }
                          placeholder="1"
                          title="For lab/practical subjects: split the class into this many simultaneous batches, each with its own teacher and room. Leave blank or 1 for no split."
                          className="w-12 rounded px-1.5 py-0.5 text-xs text-slate-500 hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                        />
                        <span className="text-xs text-slate-400">batches</span>
                        <label htmlFor={`subject-credits-${subject.id}`} className="sr-only">Credits</label>
                        <input
                          id={`subject-credits-${subject.id}`}
                          type="number"
                          min="0"
                          defaultValue={subject.credits ?? ''}
                          disabled={readOnly}
                          onBlur={(e) =>
                            Number(e.target.value || 0) !== (subject.credits ?? 0) &&
                            handleUpdateCredits(subject.id, e.target.value)
                          }
                          placeholder="Credits"
                          title="Optional, for colleges that track credits per course. Not used by the solver."
                          className="w-16 rounded px-1.5 py-0.5 text-xs text-slate-500 placeholder:text-slate-400 hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                        />
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => toggleAdvanced(subject.id)}
                      className="mt-0.5 text-[11px] text-slate-400 underline underline-offset-2 hover:text-slate-600"
                    >
                      Hide advanced
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => toggleAdvanced(subject.id)}
                    className="mt-0.5 text-[11px] text-slate-400 underline underline-offset-2 hover:text-slate-600"
                  >
                    + Advanced (room type
                    {institutionType === 'college' ? ', credits, lab batches' : ''})
                  </button>
                )}
              </td>
              <td className="py-2">
                {!readOnly && !subject._pending && (
                  <button
                    onClick={() => handleRemoveSubject(subject.id, subject.name)}
                    className="text-slate-300 hover:text-red-600"
                    title="Remove subject"
                    aria-label={`Remove subject ${subject.name}`}
                  >
                    ✕
                  </button>
                )}
              </td>
            </motion.tr>
            ))}
          </AnimatePresence>
          {subjects.length === 0 && (
            <tr>
              <td colSpan={2} className="py-4 text-sm text-slate-500">
                No subjects yet. Add one above, or import a spreadsheet.
              </td>
            </tr>
          )}
          {subjects.length > 0 && shownSubjects.length === 0 && (
            <tr>
              <td colSpan={2} className="py-4 text-sm text-slate-500">
                No subjects match "{search.trim()}".
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}


/**
 * "+ Add subject": a name, who teaches it and the room it needs, in one box -
 * the same shape as Add teacher, so the two pages work alike.
 */
function AddSubjectModal({ subjects, teachers, onClose, onAdd }) {
  const [name, setName] = useState('')
  const [teacherIds, setTeacherIds] = useState([])
  const [requiredRoomType, setRequiredRoomType] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const taken = subjects.some((x) => x.name.trim().toLowerCase() === name.trim().toLowerCase())

  function toggleTeacher(id) {
    setTeacherIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim() || taken || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await onAdd({ name: name.trim(), requiredRoomType: requiredRoomType.trim(), teacherIds })
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  const shownTeachers = [...teachers].sort((a, b) => compareNames(a.name, b.name))

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 6 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 6 }}
        transition={{ duration: 0.15, ease: 'easeOut' }}
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl"
        role="dialog"
        aria-label="Add subject"
      >
        <h3 className="text-base font-semibold">Add subject</h3>
        <form onSubmit={handleSubmit} className="mt-3 flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="new-subject-name" className="text-xs font-medium text-slate-500">
              Name
            </label>
            <input
              id="new-subject-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Subject name"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />
            {taken && <p className="text-xs text-amber-700">There's already a subject called that.</p>}
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-500">
              Teachers who teach it (optional; a subject can have more than one)
            </span>
            {shownTeachers.length === 0 ? (
              <p className="text-xs text-slate-400">
                No teachers yet. Add this subject now and tick it for teachers when you add them.
              </p>
            ) : (
              <div className="max-h-48 overflow-y-auto rounded-md border border-slate-200 p-2">
                {shownTeachers.map((t) => (
                  <label
                    key={t.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-slate-50"
                  >
                    <input type="checkbox" checked={teacherIds.includes(t.id)} onChange={() => toggleTeacher(t.id)} />
                    {t.name}
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="new-subject-room" className="text-xs font-medium text-slate-500">
              Room it needs (optional, e.g. lab)
            </label>
            <input
              id="new-subject-room"
              value={requiredRoomType}
              onChange={(e) => setRequiredRoomType(e.target.value)}
              placeholder="Leave empty for any classroom"
              title="If set, this subject can only be given a room whose type matches exactly"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="mt-1 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              disabled={!name.trim() || taken || submitting}
              className="rounded-md bg-neutral-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {submitting ? 'Adding…' : 'Add subject'}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  )
}
