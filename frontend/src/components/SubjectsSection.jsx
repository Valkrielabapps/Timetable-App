import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import BulkImportPanel from './BulkImportPanel'

/**
 * "What does your school teach" — subject name plus optional advanced
 * fields (room type, and for colleges, credits/lab batches). Deliberately
 * does not show periods/week or teacher assignment: those are two other
 * questions ("how much of it does this section need" and "who teaches
 * it"), answered on the Plan and Teachers pages respectively. Splitting
 * them out means this page only ever asks "what subjects exist," instead
 * of a single row doing five unrelated things at once (see DataEntryTab's
 * docstring for the full reasoning behind the three-way split).
 */
export default function SubjectsSection({ schoolId, subjects, onSubjectsChanged, institutionType, readOnly }) {
  const [error, setError] = useState(null)
  const [showImport, setShowImport] = useState(true)
  // Which subject rows have their "advanced" fields expanded — collapsed
  // by default since most subjects never set these; a row that already
  // has an advanced field set starts expanded so existing settings are
  // never hidden without a trace.
  const [expandedAdvanced, setExpandedAdvanced] = useState(new Set())

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

  async function handleAddSubject() {
    try {
      const created = await onSubjectsChanged.create({ school_id: schoolId, name: 'New subject' })
      return created
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRemoveSubject(id, name) {
    if (!window.confirm(`Remove "${name}"? This also removes its periods/week and teacher qualifications for this subject.`)) {
      return
    }
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
          <p className="mt-1 text-sm text-slate-500">What your school teaches — applies to every section.</p>
        </div>
        {!readOnly && (
          <button
            onClick={handleAddSubject}
            className="w-fit rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
          >
            + Add subject
          </button>
        )}
      </div>

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

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-500">
            <th className="py-2 font-medium">Subject</th>
            <th className="w-8 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {/* `initial={false}` skips the enter animation for rows already
              present when this table mounts — without it, every plain tab
              switch back to Subjects replayed a staggered fade-in for the
              *entire* list (DataEntryTab fully remounts on every top-level
              tab switch — see App.jsx's `key={tab}` — so this ran on every
              single visit, not just when a subject was actually added).
              With it, only a genuinely new row (or one being removed)
              animates; everything else just appears, instantly, matching
              the pattern TeachersSection's chips already use. */}
          <AnimatePresence initial={false}>
            {subjects.map((subject) => (
              <motion.tr
                key={subject.id}
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
                {subject._pending ? null : expandedAdvanced.has(subject.id) ? (
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
                          title="Optional — for colleges that track credits per course. Not used by the solver."
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
                No subjects yet — add one above, or import a spreadsheet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
