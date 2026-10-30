import { useState } from 'react'
import { confirmDialog } from './confirmDialog'
import SearchableSelect from './SearchableSelect'
import { sortByName, sortSections } from '../sorting'
import { blockSectionIds, groupSectionIds } from '../electiveSections'

/**
 * A section's elective blocks: subjects studied at the same time, each
 * student taking one.
 *
 * "Block 1: Physics / Accounts / Biology, 6 periods a week" means all three
 * run in the same six periods, each with its own teacher, and every student
 * is in exactly one of them. Physics and Chemistry go in different blocks
 * precisely so one student can take both.
 *
 * A block can span several sections. Grade 9 A and B both break up for the
 * Maths / History period, and everyone who chose Maths, from either section,
 * goes to one Maths class. Each subject in a block is a group with its own
 * teacher, drawn from some or all of the block's sections - so the same form
 * covers sections pooling, a big subject split into two groups, a subject one
 * section takes on its own while the others pool, and sections of different
 * grades sharing a language period. See backend/app/routers/elective_blocks.py
 * for the rules a block has to follow.
 *
 * Shown in every section the block includes, not only the one it was made in.
 */
export default function ElectiveBlocksPanel({
  schoolId,
  classGroupId,
  sectionGrade,
  // The blocks this section is in, made here or joined.
  blocks,
  // Every section, to choose who shares a block.
  classGroups = [],
  // Subjects everyone in the section takes. They can't also be options.
  commonSubjectIds,
  // The same for every section, for blocks spanning several.
  commonSubjectIdsBySection = {},
  // Every block in the school, to know what other sections already have.
  allBlocks = null,
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
  const sectionById = new Map(classGroups.map((cg) => [cg.id, cg]))
  const sectionLabel = (id) => {
    const cg = sectionById.get(id)
    return cg ? [cg.grade, cg.name].filter(Boolean).join(' ') : 'Section'
  }
  // Qualified for the subject and, when a teacher is limited to some grades,
  // for every grade in the group.
  const qualifiedFor = (subjectId, sectionIds = [classGroupId]) => {
    const grades = [...new Set(sectionIds.map((id) => sectionById.get(id)?.grade ?? sectionGrade).filter(Boolean))]
    return teachers.filter(
      (t) =>
        t.qualified_subject_ids.includes(subjectId) &&
        (!t.qualified_grades?.length || grades.every((g) => t.qualified_grades.includes(g))),
    )
  }

  async function handleSave(form) {
    const sectionIds = form.sectionIds
    const data = {
      name: form.name.trim(),
      periods_per_week: form.periodsPerWeek,
      section_ids: sectionIds,
      options: form.groups.map((g) => ({
        subject_id: g.subjectId,
        preferred_teacher_id: g.teacherId,
        label: g.label.trim() || null,
        class_group_ids: g.sectionIds.length === sectionIds.length ? null : g.sectionIds,
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
    const shared = blockSectionIds(block).length > 1
    const ok = await confirmDialog({
      title: `Delete ${block.name}?`,
      message: shared
        ? `Its subjects stop being scheduled for ${blockSectionIds(block).map(sectionLabel).join(', ')} until you add them again.`
        : 'Its subjects stop being scheduled for this section until you add them again.',
      confirmLabel: 'Delete',
      danger: true,
    })
    if (!ok) return
    setError(null)
    try {
      await mutations.delete(block.id)
    } catch (err) {
      setError(err.message)
    }
  }

  // A subject everyone in a section already takes can't also be an option
  // there. One in another block stays on offer - Maths / Economics and Maths /
  // History are two Maths classes at different times - and is just labelled.
  const unavailableFor = (blockId, sectionIds) => {
    const out = new Set()
    for (const id of sectionIds) {
      const common = id === classGroupId ? commonSubjectIds : commonSubjectIdsBySection[id] ?? []
      for (const s of common) out.add(s)
    }
    return out
  }
  const otherBlocksFor = (blockId, sectionIds) => {
    const out = new Map()
    for (const b of allBlocks ?? blocks) {
      if (b.id === blockId) continue
      for (const o of b.options) {
        if (groupSectionIds(b, o).some((id) => sectionIds.includes(id))) {
          out.set(o.subject_id, [...new Set([...(out.get(o.subject_id) ?? []), b.name])])
        }
      }
    }
    return out
  }

  const formProps = {
    subjects,
    classGroups,
    sectionLabel,
    qualifiedFor,
    unavailableFor,
    otherBlocksFor,
    onSave: handleSave,
    onCancel: () => setEditing(null),
  }

  return (
    <div className="flex flex-col gap-3 border-t border-slate-200 pt-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-base font-medium">Elective blocks</h4>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Subjects studied at the same time, each student taking one, for example
            Physics / Accounts / Biology. Every subject in a block runs in the same periods
            with its own teacher, so a block counts once towards the week. A block can
            include other sections too: their students join the same classes, for example
            9 A and 9 B taking Maths or History together.
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
          {...formProps}
          blockId={null}
          homeId={classGroupId}
          initial={{ name: `Block ${blocks.length + 1}`, periodsPerWeek: 1, sectionIds: [classGroupId], groups: [] }}
        />
      )}

      {blocks.length === 0 && editing !== 'new' && (
        <p className="text-sm text-slate-400">No elective blocks in this section.</p>
      )}

      {blocks.map((block) => {
        const sectionIds = blockSectionIds(block)
        const shared = sectionIds.length > 1
        if (editing === block.id) {
          return (
            <BlockForm
              key={block.id}
              {...formProps}
              blockId={block.id}
              homeId={block.class_group_id}
              initial={{
                name: block.name,
                periodsPerWeek: block.periods_per_week,
                sectionIds,
                groups: block.options.map((o) => ({
                  key: `o${o.id}`,
                  subjectId: o.subject_id,
                  teacherId: o.preferred_teacher_id,
                  label: o.label ?? '',
                  sectionIds: groupSectionIds(block, o),
                })),
              }}
            />
          )
        }
        return (
          <div key={block.id} className="rounded-md border border-slate-200 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm">
                <span className="font-medium">{block.name}</span>
                <span className="ml-2 text-slate-500">
                  {block.periods_per_week} period{block.periods_per_week === 1 ? '' : 's'}/week
                </span>
                {shared && (
                  <span className="ml-2 rounded bg-violet-100 px-1.5 py-0.5 text-[11px] font-medium text-violet-800">
                    Shared: {sectionIds.map(sectionLabel).join(', ')}
                  </span>
                )}
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
                const groupIds = groupSectionIds(block, o)
                const qualified = qualifiedFor(o.subject_id, groupIds)
                return (
                  <li key={o.id} className="flex flex-wrap gap-x-2">
                    <span>
                      {subjectName(o.subject_id)}
                      {o.label && <span className="text-slate-500"> ({o.label})</span>}
                    </span>
                    {shared && (
                      <span className="text-slate-500">
                        · {groupIds.length === sectionIds.length ? 'all sections' : groupIds.map(sectionLabel).join(', ')}
                      </span>
                    )}
                    <span className="text-slate-500">
                      ·{' '}
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
        )
      })}
    </div>
  )
}

let nextKey = 0
const newKey = () => `g${(nextKey += 1)}`

function BlockForm({
  blockId, homeId, initial, subjects, classGroups, sectionLabel, qualifiedFor, unavailableFor,
  otherBlocksFor = () => new Map(), onSave, onCancel,
}) {
  const [name, setName] = useState(initial.name)
  const [periodsPerWeek, setPeriodsPerWeek] = useState(String(initial.periodsPerWeek))
  const [sectionIds, setSectionIds] = useState(initial.sectionIds)
  const [groups, setGroups] = useState(initial.groups.map((g) => ({ key: g.key ?? newKey(), ...g })))
  const [showSections, setShowSections] = useState(initial.sectionIds.length > 1)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const shared = sectionIds.length > 1
  const unavailable = unavailableFor(blockId, sectionIds)
  const inOtherBlocks = otherBlocksFor(blockId, sectionIds)
  const chosen = new Set(groups.map((g) => g.subjectId))
  const offered = sortByName(subjects.filter((s) => !s._pending && (!unavailable.has(s.id) || chosen.has(s.id))))
  const homeGrade = classGroups.find((cg) => cg.id === homeId)?.grade
  // The section's own grade first: sharing a block is usually within a grade.
  const sectionChoices = [...sortSections(classGroups)].sort(
    (a, b) => (b.grade === homeGrade) - (a.grade === homeGrade),
  )

  function toggleSection(id, on) {
    if (id === homeId) return
    setSectionIds((prev) => {
      const next = on ? [...prev, id] : prev.filter((x) => x !== id)
      return classGroups.filter((cg) => next.includes(cg.id)).map((cg) => cg.id).sort((a, b) => (a === homeId ? -1 : b === homeId ? 1 : 0))
    })
    // A new section joins every group that had every section; a removed one
    // leaves every group.
    setGroups((prev) =>
      prev.map((g) => {
        if (on) return g.sectionIds.length === sectionIds.length ? { ...g, sectionIds: [...g.sectionIds, id] } : g
        return { ...g, sectionIds: g.sectionIds.filter((x) => x !== id) }
      }),
    )
  }

  function toggleSubject(subjectId, on) {
    setGroups((prev) =>
      on
        ? [...prev, { key: newKey(), subjectId, teacherId: null, label: '', sectionIds: [...sectionIds] }]
        : prev.filter((g) => g.subjectId !== subjectId),
    )
  }

  const update = (key, change) => setGroups((prev) => prev.map((g) => (g.key === key ? { ...g, ...change } : g)))

  function splitGroup(group) {
    setGroups((prev) => {
      const same = prev.filter((g) => g.subjectId === group.subjectId)
      const labelled = prev.map((g) =>
        g.subjectId === group.subjectId && !g.label ? { ...g, label: `Group ${same.indexOf(g) + 1}` } : g,
      )
      const at = labelled.findIndex((g) => g.key === group.key)
      const copy = { ...group, key: newKey(), teacherId: null, label: `Group ${same.length + 1}` }
      return [...labelled.slice(0, at + 1), copy, ...labelled.slice(at + 1)]
    })
  }

  function toggleGroupSection(group, id) {
    const has = group.sectionIds.includes(id)
    update(group.key, {
      sectionIds: has ? group.sectionIds.filter((x) => x !== id) : sectionIds.filter((x) => x === id || group.sectionIds.includes(x)),
    })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const ppw = Number(periodsPerWeek)
    // Checked here as well as on the server so the common mistakes are caught
    // without a round trip; the server still has the final word.
    if (!name.trim()) return setError('Give the block a name.')
    if (!Number.isInteger(ppw) || ppw < 1) return setError('A block needs at least 1 period a week.')
    if (!shared && groups.length < 2) {
      return setError(
        'A block needs at least two subjects. A single subject is just an ordinary subject of the section - or add other sections to teach it to them together.',
      )
    }
    if (groups.length === 0) return setError('Add at least one subject to the block.')
    const empty = groups.find((g) => g.sectionIds.length === 0)
    if (empty) {
      return setError(`Choose which sections' students take ${subjects.find((s) => s.id === empty.subjectId)?.name ?? 'each subject'}.`)
    }
    const idle = sectionIds.find((id) => !groups.some((g) => g.sectionIds.includes(id)))
    if (idle) return setError(`No subject in this block is for ${sectionLabel(idle)}. Give it one, or take it out of the block.`)
    setError(null)
    setSaving(true)
    try {
      await onSave({ name, periodsPerWeek: ppw, sectionIds, groups })
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
        <div className="mb-1 flex items-center gap-2 text-xs font-medium text-slate-500">
          Sections in this block
          {!showSections && (
            <button
              type="button"
              onClick={() => setShowSections(true)}
              className="font-medium text-violet-700 hover:text-violet-900"
            >
              + Share with other sections
            </button>
          )}
        </div>
        {showSections ? (
          <>
            <p className="mb-1 text-xs text-slate-500">
              Students from every ticked section are free at the same time and go to the same classes.
            </p>
            <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 md:grid-cols-4" role="group" aria-label="Sections in this block">
              {sectionChoices.map((cg) => (
                <label key={cg.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-white">
                  <input
                    type="checkbox"
                    checked={sectionIds.includes(cg.id)}
                    disabled={cg.id === homeId}
                    onChange={(e) => toggleSection(cg.id, e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-slate-900"
                  />
                  {sectionLabel(cg.id)}
                </label>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-600">{sectionLabel(homeId)} only</p>
        )}
      </div>

      <div>
        <div className="mb-1 text-xs font-medium text-slate-500">
          Subjects in this block (students take one)
        </div>
        {offered.length === 0 ? (
          <p className="text-sm text-slate-400">
            Every subject is already a common subject of these sections.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 md:grid-cols-3">
            {offered.map((s) => (
              <label key={s.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-white">
                <input
                  type="checkbox"
                  checked={chosen.has(s.id)}
                  onChange={(e) => toggleSubject(s.id, e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-slate-900"
                />
                {s.name}
                {inOtherBlocks.has(s.id) && (
                  <span className="text-xs text-slate-400">also in {inOtherBlocks.get(s.id).join(', ')}</span>
                )}
              </label>
            ))}
          </div>
        )}
      </div>

      {groups.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-medium text-slate-500">
            {shared ? 'Classes: who teaches each, and whose students are in it' : 'Who teaches each option'}
          </div>
          {groups.map((g) => {
            const qualified = qualifiedFor(g.subjectId, g.sectionIds.length ? g.sectionIds : sectionIds)
            const subject = subjects.find((s) => s.id === g.subjectId)
            const title = `${subject?.name ?? 'Deleted subject'}${g.label ? ` (${g.label})` : ''}`
            return (
              <div key={g.key} className="flex flex-col gap-1.5 rounded border border-slate-200 bg-white p-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="w-36 truncate font-medium">{subject?.name ?? 'Deleted subject'}</span>
                  <input
                    aria-label={`Group name for ${title}`}
                    value={g.label}
                    onChange={(e) => update(g.key, { label: e.target.value })}
                    maxLength={40}
                    placeholder="Group name (optional)"
                    className="w-40 rounded border border-slate-300 px-2 py-0.5 text-xs"
                  />
                  {qualified.length === 0 ? (
                    <span className="text-xs text-amber-700">No qualified teacher yet. Mark one on the Teachers page</span>
                  ) : (
                    <SearchableSelect
                      ariaLabel={`Teacher for ${title}`}
                      value={g.teacherId}
                      onChange={(id) => update(g.key, { teacherId: id })}
                      emptyOption={{ label: 'Any qualified (let solver choose)' }}
                      options={qualified.map((t) => ({ value: t.id, label: t.name }))}
                      className="text-xs"
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => splitGroup(g)}
                    className="text-xs font-medium text-slate-500 hover:text-slate-800"
                    title="Teach this subject as two classes at the same time, each with its own teacher"
                  >
                    Split into another group
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove ${title}`}
                    onClick={() => setGroups((prev) => prev.filter((x) => x.key !== g.key))}
                    className="text-xs font-medium text-red-600 hover:text-red-800"
                  >
                    Remove
                  </button>
                </div>
                {shared && (
                  <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={`Students in ${title}`}>
                    <span className="text-xs text-slate-500">Students from:</span>
                    {sectionIds.map((id) => (
                      <button
                        key={id}
                        type="button"
                        aria-pressed={g.sectionIds.includes(id)}
                        onClick={() => toggleGroupSection(g, id)}
                        className={`rounded-full border px-2 py-0.5 text-xs ${
                          g.sectionIds.includes(id)
                            ? 'border-slate-800 bg-slate-800 text-white'
                            : 'border-slate-300 bg-white text-slate-600 hover:border-slate-500'
                        }`}
                      >
                        {sectionLabel(id)}
                      </button>
                    ))}
                  </div>
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
