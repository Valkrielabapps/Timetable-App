import { useEffect, useState } from 'react'

const DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/**
 * A subject held at the same period for some grades only - "the class
 * teacher period is period 8 for Grades 1 to 5" while the rest of the school
 * has an ordinary lesson then. Unlike the school-wide class teacher period,
 * these are real lessons: taught by whoever the section's plan names (its
 * class teacher) and counted in that teacher's week. See
 * School.fixed_periods on the backend.
 */
export default function FixedPeriodsPanel({ grades, subjects, rules: saved, lessonsByDay, onSave, readOnly = false }) {
  const [rules, setRules] = useState(() => toRules(saved))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)
  const key = JSON.stringify(saved ?? [])
  useEffect(() => setRules(toRules(saved)), [key]) // eslint-disable-line react-hooks/exhaustive-deps

  const days = Object.keys(lessonsByDay).map(Number).sort((a, b) => a - b)
  const longest = Math.max(0, ...Object.values(lessonsByDay))
  const dirty = JSON.stringify(rules) !== JSON.stringify(toRules(saved))
  const incomplete = rules.some((r) => !r.subject_id || r.grades.length === 0)

  function update(i, patch) {
    setDone(false)
    setRules((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await onSave(rules.map((r) => ({ ...r, days: r.days.length && r.days.length < days.length ? r.days : null })))
      setDone(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (days.length === 0) return <p className="text-sm text-slate-500">Set up the timetable structure above first.</p>
  if (grades.length === 0) return <p className="text-sm text-slate-500">Add grades in the sidebar first.</p>

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-500">
        A subject that’s always in the same period for some grades only, like the class teacher period in period 8
        for Grades 1 to 5. It’s a real lesson: taught by whoever the section’s plan names (usually its class
        teacher) and counted in their week. Give the subject as many periods a week as days it’s fixed to.
      </p>

      {rules.map((rule, i) => (
        <div key={i} className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
            <select
              aria-label="Subject"
              value={rule.subject_id ?? ''}
              disabled={readOnly}
              onChange={(e) => update(i, { subject_id: e.target.value ? Number(e.target.value) : null })}
              className="rounded-md border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">Choose a subject…</option>
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <span>in period</span>
            <select
              aria-label="Period"
              value={rule.period}
              disabled={readOnly}
              onChange={(e) => update(i, { period: Number(e.target.value) })}
              className="rounded-md border border-slate-300 px-2 py-1 text-sm"
            >
              {Array.from({ length: longest }, (_, n) => n + 1).map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
            <span>on</span>
            {days.map((d) => {
              const on = rule.days.length === 0 || rule.days.includes(d)
              return (
                <button
                  key={d}
                  type="button"
                  disabled={readOnly}
                  aria-pressed={on}
                  onClick={() => {
                    const cur = rule.days.length ? rule.days : days
                    const next = on ? cur.filter((x) => x !== d) : [...cur, d].sort((a, b) => a - b)
                    update(i, { days: next.length === days.length ? [] : next })
                  }}
                  className={`rounded border px-1.5 py-0.5 text-xs ${on ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 text-slate-500'}`}
                >
                  {DAY_SHORT[d]}
                </button>
              )
            })}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs text-slate-500">For</span>
            {grades.map((g) => {
              const on = rule.grades.includes(g)
              return (
                <button
                  key={g}
                  type="button"
                  disabled={readOnly}
                  aria-pressed={on}
                  onClick={() => update(i, { grades: on ? rule.grades.filter((x) => x !== g) : [...rule.grades, g] })}
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                    on ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {g}
                </button>
              )
            })}
          </div>
          {!readOnly && (
            <button
              type="button"
              onClick={() => {
                setDone(false)
                setRules((rs) => rs.filter((_, j) => j !== i))
              }}
              className="mt-2 text-xs font-medium text-slate-500 hover:text-red-600"
            >
              Remove
            </button>
          )}
        </div>
      ))}

      {!readOnly && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setDone(false)
              setRules((rs) => [...rs, { subject_id: null, grades: [], period: Math.min(8, longest), days: [] }])
            }}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            + Add a fixed period
          </button>
          {dirty && !done && (
            <button
              type="button"
              onClick={save}
              disabled={saving || incomplete}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          )}
          {done && <span className="text-xs text-emerald-700">Saved. Generate again to apply it.</span>}
          {incomplete && <span className="text-xs text-slate-500">Choose a subject and at least one grade.</span>}
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}

function toRules(saved) {
  return (saved ?? []).map((r) => ({
    subject_id: r.subject_id ?? null,
    grades: r.grades ?? [],
    period: r.period ?? 1,
    days: r.days ?? [],
  }))
}
