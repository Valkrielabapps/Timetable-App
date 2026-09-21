import { useEffect, useState } from 'react'
import { api } from '../api'

const TYPE_LABELS = {
  workload_limit: 'Workload limit',
  availability: 'Availability',
  no_subject_period: 'Subject placement',
  require_subject_period: 'Subject placement',
  no_subject_day: 'Subject day restriction',
  require_subject_day: 'Subject day restriction',
  max_consecutive_periods: 'Consecutive periods limit',
  min_gap_between_subjects: 'Subject spacing',
  subject_sequence: 'Subject sequencing',
  scheduling_rule: 'Scheduling rule',
}

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
 */
export default function ConstraintsTab({ schoolId, classGroups, constraints, onReload, readOnly = false }) {
  const [input, setInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [scopeEditingId, setScopeEditingId] = useState(null)
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

  function classGroupLabel(cg) {
    return cg.grade ? `${cg.grade} - ${cg.name}` : cg.name
  }

  async function handleAdd(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setSubmitting(true)
    setError(null)
    try {
      await api.parseConstraint(schoolId, text)
      setInput('')
      await onReload()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
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
    if (!window.confirm(`Remove this constraint?\n\n"${description}"`)) return
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
                  {submitting ? 'Adding…' : 'Add'}
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

      <div className="flex flex-wrap gap-3">
        {constraints.map((c) => (
          <ConstraintCard
            key={c.id}
            constraint={c}
            classGroups={classGroups}
            classGroupLabel={classGroupLabel}
            isEditing={editingId === c.id}
            isEditingScope={scopeEditingId === c.id}
            readOnly={readOnly}
            onStartEdit={() => setEditingId(c.id)}
            onCancelEdit={() => setEditingId(null)}
            onSaveEdit={(text) => handleSaveEdit(c.id, text)}
            onStartScopeEdit={() => setScopeEditingId(c.id)}
            onCancelScopeEdit={() => setScopeEditingId(null)}
            onSaveScope={(ids) => handleSaveScope(c, ids)}
            onRemove={() => handleRemove(c.id, c.description)}
          />
        ))}
        {constraints.length === 0 && (
          <p className="text-sm text-slate-500">No constraints added yet.</p>
        )}
      </div>
    </div>
  )
}

function ConstraintCard({
  constraint: c,
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
    <div className="w-72 rounded-lg border border-slate-200 p-3.5">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          {TYPE_LABELS[c.type] || c.type}
        </span>
        {!readOnly && (
          <div className="flex items-center gap-2">
            <button onClick={onStartEdit} className="text-xs text-slate-400 hover:text-slate-700" title="Edit" aria-label="Edit constraint">
              ✎
            </button>
            <button onClick={onRemove} className="text-slate-300 hover:text-red-600" title="Delete" aria-label="Delete constraint">
              ✕
            </button>
          </div>
        )}
      </div>

      {isEditing ? (
        <div className="mt-2 flex flex-col gap-1.5">
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
        <p className="mt-2 text-sm leading-snug">{c.description}</p>
      )}

      {scopable && !isEditing && (
        <div className="mt-2">
          {readOnly ? (
            <p className="text-xs text-slate-500">Applies to: {scopeLabel}</p>
          ) : isEditingScope ? (
            <div className="rounded border border-slate-200 p-2">
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
          ) : (
            <button onClick={onStartScopeEdit} className="text-left text-xs text-slate-500 hover:text-slate-700">
              Applies to: <span className="underline underline-offset-2">{scopeLabel}</span>
            </button>
          )}
        </div>
      )}

      {!c.enforced && (
        <div className="mt-2 flex items-start gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-800">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-none">
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
            <path d="M12 9v4" />
            <path d="M12 17h.01" />
          </svg>
          <span>
            Saved, but not applied when generating — this won't affect the timetable.
          </span>
        </div>
      )}
      {c.conflicts && c.conflicts.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-red-600">
          {c.conflicts.map((msg, i) => (
            <li key={i}>{msg}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
