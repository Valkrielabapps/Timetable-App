import { useEffect, useState } from 'react'

// The tick-box rules on the Constraints page - see
// backend/app/services/standard_rules.py for how each one is applied.
const DEFAULTS = {
  teacher_week_max: { on: false, value: 30 },
  teacher_day_max: { on: false, value: 6 },
  teacher_spread: { on: true },
}

const RULES = [
  {
    key: 'teacher_week_max',
    before: 'No teacher has more than',
    after: 'periods in a week',
    min: 1,
    max: 80,
    hint: "A teacher with their own limit on the Teachers page keeps theirs.",
  },
  {
    key: 'teacher_day_max',
    before: 'No teacher has more than',
    after: 'periods in a day',
    min: 1,
    max: 16,
  },
  {
    key: 'teacher_spread',
    before: "Spread each teacher's periods out across the day and the week",
    hint: 'Avoids back-to-back periods and gives each teacher a similar load every day, where the timetable allows.',
  },
]

export function withDefaults(rules) {
  const out = {}
  for (const [key, def] of Object.entries(DEFAULTS)) out[key] = { ...def, ...(rules?.[key] || {}) }
  return out
}

export default function StandardRules({ rules, onSave, readOnly = false }) {
  const current = withDefaults(rules)
  const [drafts, setDrafts] = useState({})
  const [saving, setSaving] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => setDrafts({}), [rules])

  async function save(key, change) {
    setSaving(key)
    setError(null)
    try {
      await onSave({ [key]: { ...current[key], ...change } })
    } catch (e) {
      setError(e.message || 'Could not save that change.')
    } finally {
      setSaving(null)
    }
  }

  function commitNumber(rule) {
    const raw = drafts[rule.key]
    if (raw === undefined) return
    const n = Number(raw)
    if (!Number.isInteger(n) || n < rule.min || n > rule.max) {
      setError(`Choose a whole number from ${rule.min} to ${rule.max}.`)
      setDrafts((d) => ({ ...d, [rule.key]: undefined }))
      return
    }
    if (n !== current[rule.key].value) save(rule.key, { value: n })
  }

  return (
    <section className="rounded-md border border-slate-200 p-3" aria-labelledby="standard-rules-heading">
      <h4 id="standard-rules-heading" className="text-sm font-medium text-slate-800">Standard rules</h4>
      <p className="mt-0.5 text-xs text-slate-500">Tick the ones your school follows. They apply to every teacher.</p>
      <ul className="mt-2 flex flex-col gap-2">
        {RULES.map((rule) => {
          const setting = current[rule.key]
          const id = `std-${rule.key}`
          return (
            <li key={rule.key} className="flex items-start gap-2">
              <input
                id={id}
                type="checkbox"
                className="mt-0.5 h-4 w-4"
                checked={setting.on}
                disabled={readOnly || saving === rule.key}
                onChange={(e) => save(rule.key, { on: e.target.checked })}
              />
              <div className="text-sm">
                <span className="text-slate-800">
                  <label htmlFor={id}>{rule.before}</label>
                  {rule.after && (
                    <>
                      {' '}
                      <input
                        type="number"
                        aria-label={`Number of periods ${rule.after.replace('periods ', '')}`}
                        min={rule.min}
                        max={rule.max}
                        value={drafts[rule.key] ?? setting.value}
                        disabled={readOnly || saving === rule.key}
                        onChange={(e) => setDrafts((d) => ({ ...d, [rule.key]: e.target.value }))}
                        onBlur={() => commitNumber(rule)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            commitNumber(rule)
                          }
                        }}
                        className="mx-0.5 w-14 rounded border border-slate-300 px-1 py-0.5 text-sm"
                      />{' '}
                      <label htmlFor={id}>{rule.after}</label>
                    </>
                  )}
                </span>
                {rule.hint && <p className="text-xs text-slate-500">{rule.hint}</p>}
              </div>
            </li>
          )
        })}
      </ul>
      {error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}
    </section>
  )
}
