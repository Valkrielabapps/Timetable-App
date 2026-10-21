import { useEffect, useState } from 'react'

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

/**
 * Shorter school days for some grades - "Grades 1 and 2 go home after
 * period 6". Each rule names grades and how many periods they have a day,
 * with an optional different number for particular days (0 = no school that
 * day). Their sections are never timetabled after their last period; see
 * School.grade_day_limits on the backend.
 *
 * `lessonsByDay` is the school's own day length (weekday -> lessons), so the
 * choices never offer more periods than the day has.
 */
export default function GradeDayLimitsPanel({ grades, limits, lessonsByDay, onSave, readOnly = false }) {
  const [rules, setRules] = useState(() => toRules(limits))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  const key = JSON.stringify(limits ?? [])
  useEffect(() => setRules(toRules(limits)), [key]) // eslint-disable-line react-hooks/exhaustive-deps

  const days = Object.keys(lessonsByDay).map(Number).sort((a, b) => a - b)
  const longest = Math.max(0, ...Object.values(lessonsByDay))
  const usedElsewhere = (i) => new Set(rules.flatMap((r, j) => (j === i ? [] : r.grades)))
  const dirty = JSON.stringify(fromRules(rules)) !== JSON.stringify(fromRules(toRules(limits)))

  function update(i, patch) {
    setSaved(false)
    setRules((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await onSave(fromRules(rules))
      setSaved(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (days.length === 0) {
    return <p className="text-sm text-slate-500">Set up the timetable structure above first.</p>
  }
  if (grades.length === 0) {
    return <p className="text-sm text-slate-500">Add grades in the sidebar first.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-500">
        For grades that go home earlier than the rest of the school, like Grades 1 and 2. They&rsquo;re never
        timetabled after their last period.
      </p>

      {rules.map((rule, i) => {
        const taken = usedElsewhere(i)
        return (
          <div key={i} className="rounded-lg border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              {grades.map((g) => {
                const on = rule.grades.includes(g)
                const blocked = !on && taken.has(g)
                return (
                  <button
                    key={g}
                    type="button"
                    disabled={readOnly || blocked}
                    aria-pressed={on}
                    title={blocked ? 'Already in another rule' : undefined}
                    onClick={() => update(i, { grades: on ? rule.grades.filter((x) => x !== g) : [...rule.grades, g] })}
                    className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                      on
                        ? 'border-neutral-900 bg-neutral-900 text-white'
                        : 'border-slate-300 text-slate-600 hover:bg-slate-50 disabled:opacity-40'
                    }`}
                  >
                    {g}
                  </button>
                )
              })}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-700">
              <label className="flex items-center gap-2">
                Periods a day
                <select
                  aria-label="Periods a day"
                  value={rule.perDay}
                  disabled={readOnly}
                  onChange={(e) => update(i, { perDay: Number(e.target.value) })}
                  className="rounded-md border border-slate-300 px-2 py-1 text-sm"
                >
                  {range(1, Math.max(1, longest - 1)).map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
              <span className="text-slate-400">(the school day has {longest})</span>
            </div>

            <details className="mt-2" open={Object.keys(rule.byDay).length > 0}>
              <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-800">
                A different number on some days
              </summary>
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {days.map((d) => {
                  const value = rule.byDay[d] ?? ''
                  return (
                    <label key={d} className="flex items-center justify-between gap-2 text-xs text-slate-600">
                      {DAY_NAMES[d]}
                      <select
                        aria-label={`Periods on ${DAY_NAMES[d]}`}
                        value={value}
                        disabled={readOnly}
                        onChange={(e) => {
                          const byDay = { ...rule.byDay }
                          if (e.target.value === '') delete byDay[d]
                          else byDay[d] = Number(e.target.value)
                          update(i, { byDay })
                        }}
                        className="rounded-md border border-slate-300 px-1.5 py-0.5 text-xs"
                      >
                        <option value="">Same ({Math.min(rule.perDay, lessonsByDay[d])})</option>
                        <option value={0}>No school</option>
                        {range(1, lessonsByDay[d]).map((n) => (
                          <option key={n} value={n}>{n}</option>
                        ))}
                      </select>
                    </label>
                  )
                })}
              </div>
            </details>

            {!readOnly && (
              <button
                type="button"
                onClick={() => {
                  setSaved(false)
                  setRules((rs) => rs.filter((_, j) => j !== i))
                }}
                className="mt-2 text-xs font-medium text-slate-500 hover:text-red-600"
              >
                Remove this rule
              </button>
            )}
          </div>
        )
      })}

      {!readOnly && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setSaved(false)
              setRules((rs) => [...rs, { grades: [], perDay: Math.max(1, longest - 2), byDay: {} }])
            }}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            + Add a shorter day
          </button>
          {(dirty || rules.length !== (limits ?? []).length) && !saved && (
            <button
              type="button"
              onClick={save}
              disabled={saving || rules.some((r) => r.grades.length === 0)}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          )}
          {saved && <span className="text-xs text-emerald-700">Saved. Generate again to apply it.</span>}
          {rules.some((r) => r.grades.length === 0) && (
            <span className="text-xs text-slate-500">Choose at least one grade for each rule.</span>
          )}
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}

function range(a, b) {
  const out = []
  for (let n = a; n <= b; n += 1) out.push(n)
  return out
}

function toRules(limits) {
  return (limits ?? []).map((l) => ({
    grades: l.grades ?? [],
    perDay: l.periods_per_day,
    byDay: Object.fromEntries(Object.entries(l.by_day ?? {}).map(([d, n]) => [Number(d), n])),
  }))
}

function fromRules(rules) {
  return rules.map((r) => ({
    grades: r.grades,
    periods_per_day: r.perDay,
    by_day: Object.fromEntries(Object.entries(r.byDay).map(([d, n]) => [Number(d), n])),
  }))
}
