import { useMemo, useState } from 'react'
import SearchableSelect from './SearchableSelect'
import { compareNames, sortSections } from '../sorting'

/**
 * Freezing a subject: its lessons stay exactly where they are - periods,
 * teachers, rooms - in the sections chosen, and everything else is
 * regenerated around them. See backend/app/services/subject_freezing.py.
 *
 * The subjects offered, and where, come from the version on screen: a
 * subject can only be frozen where it has lessons to keep.
 *
 *   freezes    the server's list (api.listSubjectFreezes)
 *   entries    the version on screen's lessons
 *   onFreeze   ({ subject_id, scope, grades?, class_group_ids?, block_mode }) => Promise
 *   onUnfreeze (freezeId) => Promise
 */
export default function SubjectFreezePanel({
  freezes, entries, sections, canFreeze, busy, onFreeze, onUnfreeze,
}) {
  const [error, setError] = useState(null)
  const [subjectId, setSubjectId] = useState(null)
  const [scope, setScope] = useState('school')
  const [grades, setGrades] = useState([])
  const [sectionIds, setSectionIds] = useState([])
  const [blockMode, setBlockMode] = useState('subject')

  // subject id -> { name, sections: Set, blocks: Map(section id -> block entries) }
  const taught = useMemo(() => {
    const out = new Map()
    for (const e of entries) {
      if (!out.has(e.subject_id)) out.set(e.subject_id, { name: e.subject_name, sections: new Set(), blockIds: new Set() })
      const s = out.get(e.subject_id)
      s.sections.add(e.class_group_id)
      if (e.elective_block_id != null) s.blockIds.add(`${e.class_group_id}:${e.elective_block_id}`)
    }
    return out
  }, [entries])

  // Where each subject is already frozen, so the form doesn't offer it twice.
  const frozenWhere = useMemo(() => {
    const out = new Map()
    for (const f of freezes) {
      if (!out.has(f.subject_id)) out.set(f.subject_id, new Set())
      for (const id of f.class_group_ids) out.get(f.subject_id).add(id)
    }
    return out
  }, [freezes])

  const chosen = subjectId != null ? taught.get(subjectId) : null
  const subjectSections = chosen
    ? sortSections(sections.filter((cg) => chosen.sections.has(cg.id) && !frozenWhere.get(subjectId)?.has(cg.id)))
    : []
  const subjectGrades = [...new Set(subjectSections.map((cg) => cg.grade).filter(Boolean))]
  const inScope = subjectSections.filter((cg) =>
    scope === 'school' ? true : scope === 'grades' ? grades.includes(cg.grade) : sectionIds.includes(cg.id))
  const scopeHasBlock = chosen != null && inScope.some((cg) =>
    [...chosen.blockIds].some((key) => key.startsWith(`${cg.id}:`)))
  // The other subjects that share a block with this one, to name them.
  const blockMates = useMemo(() => {
    if (!chosen) return []
    const keys = chosen.blockIds
    const names = new Set()
    for (const e of entries) {
      if (e.elective_block_id != null && keys.has(`${e.class_group_id}:${e.elective_block_id}`) && e.subject_id !== subjectId) {
        names.add(e.subject_name)
      }
    }
    return [...names].sort(compareNames)
  }, [chosen, entries, subjectId])

  const chooseSubject = (id) => {
    setSubjectId(id)
    setGrades([])
    setSectionIds([])
    setBlockMode('subject')
    setError(null)
  }
  const toggle = (list, setList, value) =>
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value])

  const submit = async () => {
    setError(null)
    try {
      await onFreeze({
        subject_id: subjectId,
        scope,
        grades: scope === 'grades' ? grades : null,
        class_group_ids: scope === 'sections' ? sectionIds : null,
        block_mode: scopeHasBlock ? blockMode : 'subject',
      })
      chooseSubject(null)
      setScope('school')
    } catch (err) {
      setError(err.message)
    }
  }
  const unfreeze = async (id) => {
    setError(null)
    try {
      await onUnfreeze(id)
    } catch (err) {
      setError(err.message)
    }
  }

  const ready = chosen && inScope.length > 0
  const subjectOptions = [...taught.entries()].map(([id, s]) => ({ value: id, label: s.name }))

  return (
    <div className="flex flex-col gap-4">
      {freezes.length === 0 ? (
        <p className="text-sm text-slate-600">No subjects are frozen.</p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Frozen subjects">
          {freezes.map((f) => (
            <li key={f.id} className="rounded-md border border-sky-200 bg-white px-3 py-2 text-sm">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <span className="font-medium text-slate-900">❄ {f.subject}</span>
                  <span className="text-slate-600">
                    {' '}· {f.scope_label}
                    {f.scope !== 'sections' && ` (${f.section_count} section${f.section_count === 1 ? '' : 's'})`}
                    {f.frozen_from && ` · from ${f.frozen_from}`}
                  </span>
                  {f.in_blocks && (
                    <div className="text-xs text-slate-500">
                      {f.block_mode === 'block'
                        ? 'With its whole elective block'
                        : `Just ${f.subject} in its elective block - the other subjects' teachers can change`}
                    </div>
                  )}
                </div>
                {canFreeze && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => unfreeze(f.id)}
                    className="rounded border border-slate-300 px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    Unfreeze
                  </button>
                )}
              </div>
              {f.stale_reasons.length > 0 && (
                <div className="mt-1.5 rounded bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
                  <p className="font-medium">Out of date - generating will stop until it&rsquo;s unfrozen:</p>
                  <ul className="list-disc pl-4">
                    {f.stale_reasons.map((r) => <li key={r}>{r}</li>)}
                  </ul>
                </div>
              )}
              {f.notes.length > 0 && (
                <ul className="mt-1.5 list-disc pl-4 text-xs text-slate-600">
                  {f.notes.map((n) => <li key={n}>{n}</li>)}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}

      {canFreeze && (
        <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-3">
          <div>
            <h4 className="text-sm font-semibold text-slate-900">Freeze a subject</h4>
            <p className="text-xs text-slate-500">
              Keeps its lessons from the version on screen - same periods, teachers and rooms - and regenerates
              everything else around them.
            </p>
          </div>
          <SearchableSelect
            ariaLabel="Subject to freeze"
            value={subjectId}
            onChange={chooseSubject}
            options={subjectOptions}
            placeholder="Choose a subject…"
            className="w-full sm:w-64"
          />
          {chosen && subjectSections.length === 0 && (
            <p className="text-xs text-slate-500">{chosen.name} is already frozen everywhere it&rsquo;s taught.</p>
          )}
          {chosen && subjectSections.length > 0 && (
            <>
              <fieldset className="flex flex-col gap-1.5 text-sm">
                <legend className="mb-1 text-xs font-medium text-slate-500">Where</legend>
                {[
                  ['school', `Whole school (${subjectSections.length} section${subjectSections.length === 1 ? '' : 's'})`],
                  ['grades', 'Some grades'],
                  ['sections', 'Some sections'],
                ].map(([value, label]) => (
                  <label key={value} className="flex items-center gap-2">
                    <input type="radio" name="freeze-scope" checked={scope === value} onChange={() => setScope(value)} />
                    {label}
                  </label>
                ))}
              </fieldset>
              {scope === 'grades' && (
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm" role="group" aria-label="Grades">
                  {subjectGrades.map((g) => (
                    <label key={g} className="flex items-center gap-1.5">
                      <input type="checkbox" checked={grades.includes(g)} onChange={() => toggle(grades, setGrades, g)} />
                      {g}
                    </label>
                  ))}
                </div>
              )}
              {scope === 'sections' && (
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm" role="group" aria-label="Sections">
                  {subjectSections.map((cg) => {
                    const label = cg.grade ? `${cg.grade} - ${cg.name}` : cg.name
                    return (
                      <label key={cg.id} className="flex items-center gap-1.5">
                        <input type="checkbox" checked={sectionIds.includes(cg.id)}
                          onChange={() => toggle(sectionIds, setSectionIds, cg.id)} />
                        {label}
                      </label>
                    )
                  })}
                </div>
              )}
              {scopeHasBlock && (
                <fieldset className="flex flex-col gap-1.5 text-sm">
                  <legend className="mb-1 text-xs font-medium text-slate-500">
                    {chosen.name} is in an elective block{blockMates.length ? ` with ${blockMates.join(', ')}` : ''}
                  </legend>
                  <label className="flex items-start gap-2">
                    <input type="radio" name="freeze-block" className="mt-1" checked={blockMode === 'subject'}
                      onChange={() => setBlockMode('subject')} />
                    <span>
                      Just {chosen.name}
                      <span className="block text-xs text-slate-500">
                        The block keeps its periods; its other subjects&rsquo; teachers can change.
                      </span>
                    </span>
                  </label>
                  <label className="flex items-start gap-2">
                    <input type="radio" name="freeze-block" className="mt-1" checked={blockMode === 'block'}
                      onChange={() => setBlockMode('block')} />
                    <span>
                      The whole block
                      <span className="block text-xs text-slate-500">Every subject in it stays exactly as it is.</span>
                    </span>
                  </label>
                </fieldset>
              )}
              <div>
                <button
                  type="button"
                  disabled={!ready || busy}
                  onClick={submit}
                  className="rounded-md bg-sky-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-50"
                >
                  Freeze {chosen.name}
                  {ready && scope !== 'school' ? ` in ${inScope.length} section${inScope.length === 1 ? '' : 's'}` : ''}
                </button>
              </div>
            </>
          )}
        </div>
      )}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    </div>
  )
}
