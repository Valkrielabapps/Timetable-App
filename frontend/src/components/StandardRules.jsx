import { useEffect, useState } from 'react'

// The tick-box rules on the Constraints page - see
// backend/app/services/standard_rules.py for how each one is applied.
const DEFAULTS = {
  teacher_week_max: { on: false, value: 30 },
  teacher_day_max: { on: false, value: 6 },
  teacher_spread: { on: true },
  core_morning: { on: true, value: 5, include: [], exclude: [] },
}

// Which subjects count as demanding, guessed from the name. Mirrors
// is_demanding in backend/app/services/standard_rules.py - keep them alike.
const DEMANDING = /math|science|physics|chemistry|biology|\bsst\b|social|history|geograph|civics|political|economics|accountancy|accounts|business stud|statistics|\bevs\b|environmental/i
const NOT_DEMANDING = /\blab\b|practical|activity|club/i
export const isDemanding = (name = '') => DEMANDING.test(name) && !NOT_DEMANDING.test(name)

const RULES = [
  {
    key: 'teacher_week_max',
    before: 'No teacher has more than',
    after: 'periods in a week',
    numberLabel: 'Number of periods in a week',
    min: 1,
    max: 80,
    hint: "A teacher with their own limit on the Teachers page keeps theirs.",
  },
  {
    key: 'teacher_day_max',
    before: 'No teacher has more than',
    after: 'periods in a day',
    numberLabel: 'Number of periods in a day',
    min: 1,
    max: 16,
  },
  {
    key: 'teacher_spread',
    before: "Spread each teacher's periods out across the day and the week",
    hint: 'Avoids back-to-back periods and gives each teacher a similar load every day, where the timetable allows.',
  },
  {
    key: 'core_morning',
    before: 'Schedule demanding subjects within the first',
    after: 'periods of the day',
    numberLabel: 'Number of early periods',
    min: 1,
    max: 12,
    hint: 'Students are freshest in the morning, so these go early and lighter subjects like PE, Art and Library go later, where the timetable allows.',
    subjects: true,
  },
]

export function withDefaults(rules) {
  const out = {}
  for (const [key, def] of Object.entries(DEFAULTS)) out[key] = { ...def, ...(rules?.[key] || {}) }
  return out
}

export default function StandardRules({ rules, onSave, readOnly = false, subjects = [] }) {
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
      <p className="mt-0.5 text-xs text-slate-500">Tick the ones your school follows.</p>
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
                        aria-label={rule.numberLabel}
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
                {rule.subjects && setting.on && subjects.length > 0 && (
                  <DemandingSubjects
                    subjects={subjects}
                    setting={setting}
                    disabled={readOnly || saving === rule.key}
                    onChange={(change) => save(rule.key, change)}
                  />
                )}
              </div>
            </li>
          )
        })}
      </ul>
      {error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}
    </section>
  )
}

/** The school's subjects as toggles: which count as demanding. Starts from the
 * names (Maths, Science, Social Science ...); each click is stored as an
 * addition or removal, so a subject added later is still recognised. */
function DemandingSubjects({ subjects, setting, disabled, onChange }) {
  const include = new Set(setting.include || [])
  const exclude = new Set(setting.exclude || [])
  const counts = (s) => !exclude.has(s.id) && (include.has(s.id) || isDemanding(s.name))

  function toggle(s) {
    const inc = new Set(include)
    const exc = new Set(exclude)
    inc.delete(s.id)
    exc.delete(s.id)
    const byName = isDemanding(s.name)
    if (counts(s)) {
      if (byName) exc.add(s.id)
    } else if (!byName) {
      inc.add(s.id)
    }
    onChange({ include: [...inc], exclude: [...exc] })
  }

  return (
    <div className="mt-1.5">
      <p className="text-xs text-slate-600">Counts as demanding (click to change):</p>
      <div className="mt-1 flex flex-wrap gap-1.5" role="group" aria-label="Demanding subjects">
        {subjects.map((s) => {
          const on = counts(s)
          return (
            <button
              key={s.id}
              type="button"
              aria-pressed={on}
              disabled={disabled}
              onClick={() => toggle(s)}
              className={`rounded-full border px-2.5 py-0.5 text-xs ${
                on ? 'border-slate-800 bg-slate-800 text-white' : 'border-slate-300 bg-white text-slate-600 hover:border-slate-500'
              }`}
            >
              {s.name}
            </button>
          )
        })}
      </div>
    </div>
  )
}
