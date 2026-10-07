import { useState } from 'react'

/**
 * A section's elective blocks: subjects it studies at the same time, each
 * student taking one.
 *
 * "Block 1: Physics / Accounts / Biology, 6 periods a week" means all three
 * run in the same six periods, each with its own teacher, and every student
 * is in exactly one of them. Physics and Chemistry go in different blocks
 * precisely so one student can take both. The school decides the blocks;
 * this records them, and the solver schedules each as one unit - see
 * backend/app/routers/elective_blocks.py for the rules a block has to follow.
 *
 * A block's options are edited as one set and saved together, because every
 * way a block goes wrong - a single option, a subject twice, a subject that is
 * also one everybody takes - is about the set, not one option.
 */
export default function ElectiveBlocksPanel({
  schoolId,
  classGroupId,
  sectionGrade,
  // This section's blocks only.
  blocks,
  // Subjects everyone in the section takes. They can't also be options.
  commonSubjectIds,
  subjects,
  teachers,
  mutations,
  readOnly,
}) {
  // null | 'new' | a block id
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState(null)

  const subjectName = (id) => subjects.find((s) => s.id === id)?.name ?? 'Deleted subject'
  const teacherName = (id) => teachers.find((t) => t.id === id)?.name
  const qualifiedFor = (subjectId) =>
    teachers.filter(
      (t) =>
        t.qualified_subject_ids.includes(subjectId) &&
        (!t.qualified_grades?.length || !sectionGrade || t.qualified_grades.includes(sectionGrade)),
    )

  async function handleSave(form) {
    const data = {
      name: form.name.trim(),
      periods_per_week: form.periodsPerWeek,
      options: form.options.map((o) => ({
        subject_id: o.subjectId,
        preferred_teacher_id: o.teacherId,
      })),
    }
    if (editing === 'new') {
      await mutations.create({ ...data, school_id: schoolId, class_group_id: classGroupId })
    } else {
      await mutations.update(editing, data)
    }
    setEditing(null)
  }

  async function handleDelete(block) {
    if (
      !window.confirm(
        `Delete ${block.name}? Its subjects stop being scheduled for this section until you add them again.`,
      )
    ) {
      return
    }
    setError(null)
    try {
      await mutations.delete(block.id)
    } catch (err) {
      setError(err.message)
    }
  }

  // A subject already an option in another of this section's blocks can't be
  // offered again, and neither can one everybody takes.
  const unavailableFor = (blockId) =>
    new Set([
      ...commonSubjectIds,
      ...blocks.filter((b) => b.id !== blockId).flatMap((b) => b.options.map((o) => o.subject_id)),
    ])

  return (
    <div className="flex flex-col gap-3 border-t border-slate-200 pt-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-base font-medium">Elective blocks</h4>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Subjects this section studies at the same time, each student taking one — for
            example Physics / Accounts / Biology. Every option in a block runs in the same
            periods with its own teacher, so a block counts once towards the week.
          </p>
        </div>
        {!readOnly && editing === null && (
          <button
            onClick={() => {
              setError(null)
              setEditing('new')
            }}
            className="flex-none rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            + Add elective block
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {editing === 'new' && (
        <BlockForm
          initial={{ name: `Block ${blocks.length + 1}`, periodsPerWeek: 1, options: [] }}
          subjects={subjects}
          unavailable={unavailableFor(null)}
          qualifiedFor={qualifiedFor}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      )}

      {blocks.length === 0 && editing !== 'new' && (
        <p className="text-sm text-slate-400">No elective blocks in this section.</p>
      )}

      {blocks.map((block) =>
        editing === block.id ? (
          <BlockForm
            key={block.id}
            initial={{
              name: block.name,
              periodsPerWeek: block.periods_per_week,
              options: block.options.map((o) => ({
                subjectId: o.subject_id,
                teacherId: o.preferred_teacher_id,
              })),
            }}
            subjects={subjects}
            unavailable={unavailableFor(block.id)}
            qualifiedFor={qualifiedFor}
            onSave={handleSave}
            onCancel={() => setEditing(null)}
          />
        ) : (
          <div key={block.id} className="rounded-md border border-slate-200 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm">
                <span className="font-medium">{block.name}</span>
                <span className="ml-2 text-slate-500">
                  {block.periods_per_week} period{block.periods_per_week === 1 ? '' : 's'}/week
                </span>
              </div>
              {!readOnly && editing === null && (
                <div className="flex gap-2 text-xs">
                  <button
                    onClick={() => {
                      setError(null)
                      setEditing(block.id)
                    }}
                    className="font-medium text-slate-600 hover:text-slate-900"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(block)}
                    className="font-medium text-red-600 hover:text-red-800"
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {block.options.map((o) => {
                const qualified = qualifiedFor(o.subject_id)
                return (
                  <li key={o.id} className="flex flex-wrap gap-x-2">
                    <span>{subjectName(o.subject_id)}</span>
                    <span className="text-slate-500">
                      —{' '}
                      {o.preferred_teacher_id
                        ? teacherName(o.preferred_teacher_id) ?? 'Any qualified teacher'
                        : qualified.length === 1
                        ? qualified[0].name
                        : 'Any qualified teacher'}
                    </span>
                    {qualified.length === 0 && (
                      <span className="text-xs text-amber-700">No qualified teacher yet</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        ),
      )}
    </div>
  )
}

function BlockForm({ initial, subjects, unavailable, qualifiedFor, onSave, onCancel }) {
  const [name, setName] = useState(initial.name)
  const [periodsPerWeek, setPeriodsPerWeek] = useState(String(initial.periodsPerWeek))
  const [options, setOptions] = useState(initial.options)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const chosen = new Set(options.map((o) => o.subjectId))
  const offered = subjects.filter((s) => !s._pending && (!unavailable.has(s.id) || chosen.has(s.id)))

  function toggle(subjectId, on) {
    setOptions((prev) =>
      on ? [...prev, { subjectId, teacherId: null }] : prev.filter((o) => o.subjectId !== subjectId),
    )
  }

  function setTeacher(subjectId, teacherId) {
    setOptions((prev) => prev.map((o) => (o.subjectId === subjectId ? { ...o, teacherId } : o)))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const ppw = Number(periodsPerWeek)
    // Checked here as well as on the server so the common mistakes are caught
    // without a round trip; the server still has the final word.
    if (!name.trim()) return setError('Give the block a name.')
    if (!Number.isInteger(ppw) || ppw < 1) return setError('A block needs at least 1 period a week.')
    if (options.length < 2) {
      return setError(
        'A block needs at least two subjects — a single subject is just an ordinary subject of the section.',
      )
    }
    setError(null)
    setSaving(true)
    try {
      await onSave({ name, periodsPerWeek: ppw, options })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      // The checks in handleSubmit say what is wrong in words; the browser's
      // own tooltip for min="1" would pre-empt them with less.
      noValidate
      aria-label="Elective block"
      className="flex flex-col gap-3 rounded-md border border-slate-300 bg-slate-50/60 p-3"
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={60}
            className="w-48 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
          Periods/week
          <input
            type="number"
            min="1"
            max="60"
            value={periodsPerWeek}
            onChange={(e) => setPeriodsPerWeek(e.target.value)}
            className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800"
          />
        </label>
      </div>

      <div>
        <div className="mb-1 text-xs font-medium text-slate-500">
          Subjects in this block (students take one)
        </div>
        {offered.length === 0 ? (
          <p className="text-sm text-slate-400">
            Every subject is already taken by the whole section or another block.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 md:grid-cols-3">
            {offered.map((s) => (
              <label key={s.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-white">
                <input
                  type="checkbox"
                  checked={chosen.has(s.id)}
                  onChange={(e) => toggle(s.id, e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-slate-900"
                />
                {s.name}
              </label>
            ))}
          </div>
        )}
      </div>

      {options.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs font-medium text-slate-500">Who teaches each option</div>
          {options.map((o) => {
            const qualified = qualifiedFor(o.subjectId)
            const subject = subjects.find((s) => s.id === o.subjectId)
            return (
              <div key={o.subjectId} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="w-40 truncate">{subject?.name ?? 'Deleted subject'}</span>
                {qualified.length === 0 ? (
                  <span className="text-xs text-amber-700">
                    No qualified teacher yet — mark one on the Teachers page
                  </span>
                ) : (
                  <select
                    aria-label={`Teacher for ${subject?.name ?? 'option'}`}
                    value={o.teacherId ?? ''}
                    onChange={(e) =>
                      setTeacher(o.subjectId, e.target.value ? Number(e.target.value) : null)
                    }
                    className="rounded border border-slate-300 bg-white px-1.5 py-1 text-xs text-slate-700"
                  >
                    <option value="">Any qualified (let solver choose)</option>
                    {qualified.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            )
          })}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="text-xs font-medium text-slate-500 hover:text-slate-700">
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save block'}
        </button>
      </div>
    </form>
  )
}
