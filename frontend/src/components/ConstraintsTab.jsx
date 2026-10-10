import { useEffect, useState } from 'react'
import { api } from '../api'
import ConstraintInterpretation from './ConstraintInterpretation.jsx'
import { confirmDialog } from './confirmDialog'
import { useTimetable, useTimetables } from '../hooks/useSchoolData'
import { filterOptions, filtersActive, NO_FILTERS, organise } from '../constraintGroups'

// Types whose parameters include an optional class_group_ids scope —
// these are the ones that get the "Applies to" line and scope editor.
// The other types (workload_limit, availability) are always about one
// specific teacher, not a set of sections, so scoping doesn't apply.
//
// max_consecutive_periods is a special case: it's only actually scopable
// when it's the subject variant (parameters.subject_id set). The teacher
// variant (parameters.teacher_id set) caps that teacher's whole schedule
// and ignores any class_group_ids you'd set here — see isActuallyScopable
// below, which checks the card's own parameters rather than just its type.
const SCOPABLE_TYPES = new Set([
  'no_subject_period',
  'require_subject_period',
  'no_subject_day',
  'require_subject_day',
  'max_consecutive_periods',
  'min_gap_between_subjects',
  'max_subject_periods_per_day',
  'subject_sequence',
])

/**
 * Plain-English constraint entry. Text is sent to
 * POST /api/constraints/parse (see backend/app/routers/constraints.py),
 * which tries Claude first (backend/app/services/llm_constraint_parser.py)
 * for flexible phrasing and richer constraint types — including rules
 * scoped to one grade/section ("Grade 3 shouldn't have Math last period")
 * and consecutive-period limits ("no more than 2 PE periods in a row") —
 * and silently falls back to a regex parser if no API key is configured or
 * the call fails, so constraint entry never just breaks. Each saved
 * A constraint is either a rule (is_hard) or a preference. A preference is
 * applied as a weighted penalty rather than a hard requirement: the solver
 * avoids breaking it, but will if that is the only way to fit everything in.
 * Badged on the card, because a preference that looks identical to a rule
 * sets up exactly the wrong expectation about what the timetable guarantees.
 *
 * constraint comes back with `enforced` so the card can honestly say
 * whether the solver actually applies it, regardless of which parser
 * produced it.
 *
 * "Got several rules at once? Add them all together" switches to a
 * textarea and POSTs the whole block to POST /api/constraints/batch in
 * one request instead of one rule at a time — the backend tries to split
 * it into distinct rules itself (via a batch-oriented LLM call) and falls
 * back to treating each non-blank line as its own rule if that's
 * unavailable, so the placeholder text below recommends one rule per
 * line as the safest input shape either way.
 *
 * Each card also supports editing in place (rewording re-parses via
 * PUT /{id}/reparse, keeping the same id), an explicit "Applies to" line
 * with a scope editor for the rule types that support being scoped to
 * specific sections (PUT /{id} with an updated parameters.class_group_ids),
 * and `conflicts` — server-computed warnings when this constraint directly
 * contradicts another one already saved (two "must be" position rules for
 * the same subject, or two "must be"/"must not be" day rules for the same
 * subject, that can never both be true).
 *
 * Saved rules are listed grouped by who they are about - teachers, sections,
 * subjects, the whole school - with anything that needs fixing pulled to the
 * top, and a search box and filters over all of them. See
 * src/constraintGroups.js for how a rule is filed.
 */
export default function ConstraintsTab({ schoolId, classGroups, constraints, onReload, readOnly = false }) {
  const [input, setInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [scopeEditingId, setScopeEditingId] = useState(null)
  // { typed, interpretation } while a rule is waiting to be confirmed, null
  // otherwise. Nothing is saved until it clears.
  const [pending, setPending] = useState(null)
  const [confirming, setConfirming] = useState(false)
  // Batch entry ("add several rules at once") is a separate mode rather
  // than trying to detect multi-line input in the single-rule form —
  // keeping them distinct means the single-rule flow's behavior (and its
  // POST /parse call) never has to change to accommodate this.
  const [batchMode, setBatchMode] = useState(false)
  const [batchInput, setBatchInput] = useState('')
  const [batchSubmitting, setBatchSubmitting] = useState(false)
  // Short-lived confirmation ("Added 3 constraints") shown after a batch
  // submit — the new cards themselves already show up in the list below
  // once onReload() finishes, so this is just feedback that the paste
  // actually did something, not a second source of truth for what was
  // created.
  const [batchResultCount, setBatchResultCount] = useState(null)
  const [filters, setFilters] = useState(NO_FILTERS)
  // Groups the admin opened or closed by hand, over the default below.
  const [openOverrides, setOpenOverrides] = useState({})

  // Rules the current timetable breaks - normally none, but a hand move can
  // pass every physical check and still break one. Read from the same cached
  // query the Timetable tab uses, so this costs nothing when it is warm.
  const { data: timetableList = [] } = useTimetables(schoolId)
  const latestTimetableId =
    timetableList.length > 0 ? timetableList.reduce((a, b) => (b.id > a.id ? b : a)).id : null
  const { data: timetable = null } = useTimetable(latestTimetableId)
  const violatedIds = new Set(
    (timetable?.status === 'draft' ? timetable.violations ?? [] : []).map((v) => v.constraint_id),
  )

  const organised = organise(constraints, { violatedIds, filters })
  const options = filterOptions(constraints)
  // A short list reads fine opened up; a long one is a wall again unless its
  // groups start closed. Searching or filtering opens everything, since the
  // point is then to see what matched.
  const openByDefault = filtersActive(filters) || constraints.length <= 12
  const isOpen = (key) => openOverrides[key] ?? openByDefault
  const toggle = (key) => setOpenOverrides((prev) => ({ ...prev, [key]: !isOpen(key) }))

  // A rule about two teachers is listed under both, so editing state is kept
  // per row rather than per rule - otherwise both copies open at once.
  function renderRow(c, place, reasons = []) {
    const rowKey = `${place}|${c.id}`
    return (
      <ConstraintRow
        key={rowKey}
        constraint={c}
        reasons={reasons}
        classGroups={classGroups}
        classGroupLabel={classGroupLabel}
        isEditing={editingId === rowKey}
        isEditingScope={scopeEditingId === rowKey}
        readOnly={readOnly}
        onStartEdit={() => setEditingId(rowKey)}
        onCancelEdit={() => setEditingId(null)}
        onSaveEdit={(text) => handleSaveEdit(c.id, text)}
        onStartScopeEdit={() => setScopeEditingId(rowKey)}
        onCancelScopeEdit={() => setScopeEditingId(null)}
        onSaveScope={(ids) => handleSaveScope(c, ids)}
        onRemove={() => handleRemove(c.id, c.description)}
      />
    )
  }

  function classGroupLabel(cg) {
    return cg.grade ? `${cg.grade} - ${cg.name}` : cg.name
  }

  // Entering one rule is two steps now: read it back, then save what was read.
  // See ConstraintInterpretation.jsx for why that is not a politeness - a
  // misread rule no longer fails visibly, it schedules the wrong thing
  // faithfully, and the person who typed the sentence is the only one who can
  // tell. `pending` holds the rule awaiting that answer.
  async function handleAdd(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setSubmitting(true)
    setError(null)
    try {
      setPending({ typed: text, interpretation: await api.interpretConstraint(schoolId, text) })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleConfirm() {
    if (!pending?.interpretation?.rule) return
    setConfirming(true)
    setError(null)
    try {
      await api.confirmConstraint(schoolId, pending.interpretation.rule, pending.typed)
      setPending(null)
      setInput('')
      await onReload()
    } catch (err) {
      setError(err.message)
    } finally {
      setConfirming(false)
    }
  }

  // Rewording puts the original text back in the box rather than clearing it:
  // the admin is usually changing a word or two, and retyping the whole rule
  // is enough friction to make accepting a wrong reading the easier option.
  function handleReword() {
    setInput(pending?.typed ?? '')
    setPending(null)
    setError(null)
  }

  async function handleBatchAdd(e) {
    e.preventDefault()
    const text = batchInput.trim()
    if (!text) return
    setBatchSubmitting(true)
    setError(null)
    setBatchResultCount(null)
    try {
      const created = await api.parseConstraintsBatch(schoolId, text)
      setBatchInput('')
      setBatchResultCount(created.length)
      await onReload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBatchSubmitting(false)
    }
  }

  async function handleRemove(id, description) {
    const ok = await confirmDialog({
      title: 'Remove this constraint?',
      message: 'The solver stops applying it from the next timetable you generate.',
      detail: description,
      confirmLabel: 'Remove',
      danger: true,
    })
    if (!ok) return
    setError(null)
    try {
      await api.deleteConstraint(id)
      await onReload()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSaveEdit(id, text) {
    if (!text.trim()) return
    setError(null)
    try {
      await api.reparseConstraint(id, text.trim())
      setEditingId(null)
      await onReload()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSaveScope(constraint, selectedIds) {
    setError(null)
    try {
      const parameters = { ...constraint.parameters }
      if (selectedIds.length > 0) {
        parameters.class_group_ids = selectedIds
      } else {
        delete parameters.class_group_ids // empty selection = whole school
      }
      await api.updateConstraint(constraint.id, { parameters })
      setScopeEditingId(null)
      await onReload()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <div>
        <h3 className="text-lg font-medium">Constraints</h3>
        <p className="mt-1 text-sm text-slate-500">
          Describe scheduling rules in plain English — we'll turn them into
          structured constraints.
        </p>
      </div>

      {!readOnly && (
        <div className="flex flex-col gap-1.5">
          {batchMode ? (
            <form onSubmit={handleBatchAdd} className="flex flex-col gap-1.5 rounded-md border border-slate-300 p-3">
              <textarea
                autoFocus
                value={batchInput}
                onChange={(e) => setBatchInput(e.target.value)}
                rows={4}
                placeholder={
                  'One rule per line works best, e.g.\n' +
                  "Math can't immediately follow PE\n" +
                  'Priya Sharma is not available on Wednesdays\n' +
                  'No more than 2 PE periods in a row'
                }
                className="w-full resize-y text-sm focus:outline-none"
              />
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => {
                    setBatchMode(false)
                    setBatchResultCount(null)
                  }}
                  className="text-xs text-slate-500 underline underline-offset-2 hover:text-slate-700"
                >
                  Back to one at a time
                </button>
                <button
                  disabled={batchSubmitting}
                  className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
                >
                  {batchSubmitting ? 'Adding…' : 'Add all'}
                </button>
              </div>
            </form>
          ) : pending ? (
            <ConstraintInterpretation
              typed={pending.typed}
              interpretation={pending.interpretation}
              saving={confirming}
              onConfirm={handleConfirm}
              onReword={handleReword}
              onCancel={() => {
                setPending(null)
                setInput('')
              }}
            />
          ) : (
            <>
              <form onSubmit={handleAdd} className="flex items-center gap-2.5 rounded-md border border-slate-300 py-1.5 pl-3.5 pr-1.5">
                <span className="text-slate-400">✦</span>
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="e.g. Math can't immediately follow PE, or Priya Sharma is not available on Wednesdays"
                  className="flex-1 py-1 text-sm focus:outline-none"
                />
                <button
                  disabled={submitting}
                  className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
                >
                  {submitting ? 'Reading…' : 'Add'}
                </button>
              </form>
              <button
                type="button"
                onClick={() => setBatchMode(true)}
                className="self-start text-xs text-slate-500 underline underline-offset-2 hover:text-slate-700"
              >
                Got several rules at once? Add them all together
              </button>
            </>
          )}
          {batchResultCount !== null && (
            <p className="text-xs text-emerald-700">
              Added {batchResultCount} constraint{batchResultCount === 1 ? '' : 's'} — check below for any marked
              as not yet enforced or conflicting.
            </p>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      {constraints.length === 0 ? (
        <p className="text-sm text-slate-500">No constraints added yet.</p>
      ) : (
        <div className="flex flex-col gap-5">
          <FilterBar
            filters={filters}
            onChange={setFilters}
            options={options}
            shown={organised.shown}
            total={constraints.length}
          />

          {organised.shown === 0 && (
            <p className="text-sm text-slate-500">No rules match.</p>
          )}

          {organised.attention.length > 0 && (
            <section aria-label="Needs attention" className="rounded-md border border-amber-300">
              <h4 className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900">
                Needs attention
                <span className="font-normal text-amber-700">{organised.attention.length}</span>
              </h4>
              <ul className="divide-y divide-slate-100">
                {organised.attention.map(({ constraint, reasons }) => renderRow(constraint, 'attention', reasons))}
              </ul>
            </section>
          )}

          {organised.categories.map((cat) => (
            <section key={cat.key} aria-label={cat.label} className="flex flex-col gap-1.5">
              <h4 className="flex items-center gap-2 text-sm font-medium text-slate-700">
                {cat.label}
                <span className="font-normal text-slate-400">{cat.count}</span>
              </h4>
              <div className="divide-y divide-slate-200 rounded-md border border-slate-200">
                {cat.groups.map((group) => {
                  const key = `${cat.key}:${group.name}`
                  // Whole school has nothing to group by, so its rules sit
                  // straight in the category.
                  if (group.name === null) {
                    return (
                      <ul key={key} className="divide-y divide-slate-100">
                        {group.items.map((c) => renderRow(c, key))}
                      </ul>
                    )
                  }
                  const open = isOpen(key)
                  return (
                    <div key={key}>
                      <button
                        type="button"
                        aria-expanded={open}
                        onClick={() => toggle(key)}
                        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-slate-50"
                      >
                        <span className="font-medium text-slate-700">{group.name}</span>
                        <span className="flex items-center gap-2 text-xs text-slate-400">
                          {group.items.length} rule{group.items.length === 1 ? '' : 's'}
                          <span aria-hidden="true">{open ? '▾' : '▸'}</span>
                        </span>
                      </button>
                      {open && (
                        <ul className="divide-y divide-slate-100 border-t border-slate-100 bg-slate-50/40">
                          {group.items.map((c) => renderRow(c, key))}
                        </ul>
                      )}
                    </div>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Search box and filters over every saved rule.
 *
 * Only offers the teachers, subjects and sections that some rule actually
 * mentions - a dropdown of the whole staff list would mostly lead to empty
 * results.
 */
function FilterBar({ filters, onChange, options, shown, total }) {
  const set = (field) => (value) => onChange({ ...filters, [field]: value })
  const active = filtersActive(filters)
  const select = (label, field, values, allLabel) =>
    values.length > 0 && (
      <select
        aria-label={label}
        value={filters[field]}
        onChange={(e) => set(field)(e.target.value)}
        className="rounded-md border border-slate-300 px-2 py-1.5 text-xs text-slate-700"
      >
        <option value="">{allLabel}</option>
        {values.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
    )

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        aria-label="Search rules"
        placeholder="Search rules"
        value={filters.text}
        onChange={(e) => set('text')(e.target.value)}
        className="w-48 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus:border-neutral-900 focus:outline-none"
      />
      {select('Filter by teacher', 'teacher', options.teachers, 'All teachers')}
      {select('Filter by subject', 'subject', options.subjects, 'All subjects')}
      {select('Filter by section', 'section', options.sections, 'All sections')}
      <div className="inline-flex rounded-md border border-slate-300 p-0.5 text-xs">
        {[
          ['all', 'All'],
          ['rules', 'Rules'],
          ['preferences', 'Preferences'],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={filters.strength === value}
            onClick={() => set('strength')(value)}
            className={`rounded px-2.5 py-1 ${
              filters.strength === value ? 'bg-neutral-900 text-white' : 'text-slate-600'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {active && (
        <button
          type="button"
          onClick={() => onChange(NO_FILTERS)}
          className="text-xs text-slate-500 underline underline-offset-2 hover:text-slate-700"
        >
          Clear
        </button>
      )}
      <span className="ml-auto text-xs text-slate-400">
        {active ? `${shown} of ${total} rules` : `${total} rule${total === 1 ? '' : 's'}`}
      </span>
    </div>
  )
}

function ConstraintRow({
  constraint: c,
  reasons = [],
  classGroups,
  classGroupLabel,
  isEditing,
  isEditingScope,
  readOnly = false,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onStartScopeEdit,
  onCancelScopeEdit,
  onSaveScope,
  onRemove,
}) {
  const [editText, setEditText] = useState(c.description || '')
  const [selectedIds, setSelectedIds] = useState(c.parameters?.class_group_ids || [])

  useEffect(() => {
    setEditText(c.description || '')
  }, [c.description, isEditing])

  useEffect(() => {
    setSelectedIds(c.parameters?.class_group_ids || [])
  }, [c.parameters, isEditingScope])

  // See the SCOPABLE_TYPES comment above: a teacher-variant
  // max_consecutive_periods row (parameters.teacher_id set) caps that
  // teacher's whole schedule and isn't scoped to class groups, even
  // though the *type* is otherwise scopable for its subject variant.
  const scopable = SCOPABLE_TYPES.has(c.type) && !(c.type === 'max_consecutive_periods' && c.parameters?.teacher_id)
  const scopeIds = c.parameters?.class_group_ids
  const scopeLabel = !scopeIds
    ? 'Whole school'
    : classGroups
        .filter((cg) => scopeIds.includes(cg.id))
        .map(classGroupLabel)
        .join(', ') || 'Whole school'

  function toggleId(id) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  return (
    <li className="px-3 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {isEditing ? (
            <div className="flex flex-col gap-1.5">
              <textarea
                autoFocus
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                rows={3}
                className="w-full rounded border border-slate-300 p-1.5 text-sm focus:border-neutral-900 focus:outline-none"
              />
              <div className="flex gap-1.5">
                <button
                  onClick={() => onSaveEdit(editText)}
                  className="rounded bg-neutral-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-neutral-700"
                >
                  Save
                </button>
                <button onClick={onCancelEdit} className="rounded border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm leading-snug">{c.description}</p>
          )}

          {(c.is_hard === false || reasons.length > 0 || (scopable && !isEditing)) && (
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              {reasons.map((reason) => (
                <span
                  key={reason}
                  className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900"
                >
                  {reason}
                </span>
              ))}
              {c.is_hard === false && (
                <span
                  className="rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-800"
                  title="The timetable will avoid breaking this, but may do so if there is no other way to fit everything in."
                >
                  Preference
                </span>
              )}
              {scopable && !isEditing && !isEditingScope && (
                readOnly ? (
                  <span className="text-xs text-slate-500">Applies to: {scopeLabel}</span>
                ) : (
                  <button onClick={onStartScopeEdit} className="text-left text-xs text-slate-500 hover:text-slate-700">
                    Applies to: <span className="underline underline-offset-2">{scopeLabel}</span>
                  </button>
                )
              )}
            </div>
          )}

          {scopable && !isEditing && isEditingScope && !readOnly && (
            <div className="mt-2 rounded border border-slate-200 p-2">
              <p className="mb-1 text-xs text-slate-500">Applies to (none selected = whole school):</p>
              <div className="max-h-32 space-y-1 overflow-y-auto">
                {classGroups.map((cg) => (
                  <label key={cg.id} className="flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(cg.id)}
                      onChange={() => toggleId(cg.id)}
                    />
                    {classGroupLabel(cg)}
                  </label>
                ))}
              </div>
              <div className="mt-1.5 flex gap-1.5">
                <button
                  onClick={() => onSaveScope(selectedIds)}
                  className="rounded bg-neutral-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-neutral-700"
                >
                  Save
                </button>
                <button onClick={onCancelScopeEdit} className="rounded border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {!c.enforced && (
            <p className="mt-1.5 text-xs text-amber-800">
              Saved, but not applied when generating — this won't affect the timetable.
            </p>
          )}
          {c.conflicts && c.conflicts.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-red-600">
              {c.conflicts.map((msg, i) => (
                <li key={i}>{msg}</li>
              ))}
            </ul>
          )}
        </div>

        {!readOnly && (
          <div className="flex flex-none items-center gap-2 pt-0.5">
            <button onClick={onStartEdit} className="text-xs text-slate-400 hover:text-slate-700" title="Edit" aria-label="Edit constraint">
              ✎
            </button>
            <button onClick={onRemove} className="text-slate-300 hover:text-red-600" title="Delete" aria-label="Delete constraint">
              ✕
            </button>
          </div>
        )}
      </div>
    </li>
  )
}
