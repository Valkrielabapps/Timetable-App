import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import {
  DAY_FULL,
  DAY_SHORT,
  DEFAULT_STRUCTURE,
  fromServer,
  layoutDay,
  periodsOn,
  zeroIsNumbered,
} from '../timetableStructure'

/**
 * The school's week, set up once.
 *
 * Replaces adding every period of every day by hand ("Monday, slot 3") -
 * forty-eight rows for a six-day, eight-period school, and all of them to
 * edit again when lunch moved. Here the admin says what a day looks like:
 * which days, how many periods, where the breaks fall, and whether there is
 * a class teacher period and a zero period. Saving makes the periods (see
 * backend/app/services/timetable_structure.py) and keeps every existing one
 * that still has a place, so teacher unavailability and saved rules keep
 * pointing at the same lessons.
 *
 * Only lessons are numbered, so the class teacher period and breaks never
 * shift "period 1". A zero period is a slot of its own when it's the same
 * for the whole school every day; otherwise it is an ordinary numbered
 * period kept free for the grades it belongs to, and each day gains one.
 */

// Last structure fetched (or saved) per school, kept for the browser session.
// The panel is unmounted every time the admin leaves Setup, and fetching it
// again each time is what showed "Loading…" for a second or two on every
// visit. Now a revisit draws the cached week straight away and refreshes it
// in the background (stale-while-revalidate); the refresh only replaces what
// is on screen if the admin hasn't started editing.
const structureCache = new Map()

function fetchStructure(schoolId) {
  return api.getTimetableStructure(schoolId).then((r) => {
    structureCache.set(schoolId, r)
    return r
  })
}

/** Warm the cache before Setup is opened (App calls this on school select). */
export function prefetchTimetableStructure(schoolId) {
  if (schoolId == null || structureCache.has(schoolId)) return
  fetchStructure(schoolId).catch(() => {})
}

export default function TimetableStructurePanel({ schoolId, grades, onSaved, readOnly = false }) {
  const cached = structureCache.get(schoolId)
  const [structure, setStructure] = useState(() => (cached ? fromServer(cached.structure) : DEFAULT_STRUCTURE))
  const [loaded, setLoaded] = useState(!!cached)
  const [hasPeriods, setHasPeriods] = useState(cached ? cached.structure != null : false)
  const [irregular, setIrregular] = useState(cached ? cached.irregular : false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)
  const edited = useRef(false)

  useEffect(() => {
    let cancelled = false
    edited.current = false
    const fromCache = structureCache.get(schoolId)
    if (fromCache) {
      setStructure(fromServer(fromCache.structure))
      setHasPeriods(fromCache.structure != null)
      setIrregular(fromCache.irregular)
      setLoaded(true)
    } else {
      setLoaded(false)
    }
    fetchStructure(schoolId)
      .then((r) => {
        if (cancelled || edited.current) return
        setStructure(fromServer(r.structure))
        setHasPeriods(r.structure != null)
        setIrregular(r.irregular)
      })
      .catch((err) => !cancelled && !fromCache && setError(err.message))
      .finally(() => !cancelled && setLoaded(true))
    return () => {
      cancelled = true
    }
  }, [schoolId])

  const update = (patch) => {
    edited.current = true
    setReport(null)
    setStructure((prev) => ({ ...prev, ...patch }))
  }
  const s = structure
  const n = Number(s.periods_per_day) || 1
  const numbered = zeroIsNumbered(s)
  // Numbered slots on a full day - what breaks and the class teacher period
  // can come after.
  const fullDay = n + (numbered ? 1 : 0)

  async function handleSave() {
    setSaving(true)
    setError(null)
    setReport(null)
    try {
      const r = await api.saveTimetableStructure(schoolId, {
        ...s,
        periods_per_day: n,
        breaks: s.breaks.map((b) => ({ after: Number(b.after), label: b.label || 'Break' })),
      })
      setStructure(fromServer(r.structure))
      structureCache.set(schoolId, { structure: r.structure, irregular: false })
      edited.current = false
      setReport(r.report)
      setHasPeriods(true)
      setIrregular(false)
      await onSaved?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return <p className="text-sm text-slate-400">Loading…</p>

  return (
    <div className="flex flex-col gap-5">
      {irregular && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Your current periods don't follow one pattern on every day. Below is the pattern of your
          fullest day - saving will make every working day follow it.
        </p>
      )}

      <fieldset disabled={readOnly} className="flex flex-col gap-5">
        <Row label="Working days">
          <div className="flex flex-wrap gap-1.5">
            {DAY_SHORT.map((name, d) => {
              const on = s.days.includes(d)
              return (
                <button
                  key={d}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    const days = on ? s.days.filter((x) => x !== d) : [...s.days, d].sort((a, b) => a - b)
                    const short_days = { ...s.short_days }
                    if (on) delete short_days[d]
                    update({ days, short_days })
                  }}
                  className={`rounded-md border px-2.5 py-1 text-sm ${
                    on ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 text-slate-600'
                  }`}
                >
                  {name}
                </button>
              )
            })}
          </div>
        </Row>

        <Row label="Periods per day">
          <input
            type="number"
            min="1"
            max="16"
            aria-label="Periods per day"
            value={s.periods_per_day}
            onChange={(e) => update({ periods_per_day: e.target.value === '' ? '' : Number(e.target.value) })}
            className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm"
          />
          <ShortDays s={s} update={update} />
        </Row>

        <Row label="Breaks">
          <div className="flex flex-col gap-1.5">
            {s.breaks.map((b, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-slate-500">After period</span>
                <select
                  aria-label={`Break ${i + 1} comes after`}
                  value={b.after}
                  onChange={(e) =>
                    update({ breaks: s.breaks.map((x, j) => (j === i ? { ...x, after: Number(e.target.value) } : x)) })
                  }
                  className="rounded-md border border-slate-300 px-1.5 py-1 text-sm"
                >
                  {range(1, fullDay - 1).map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
                <input
                  aria-label={`Break ${i + 1} name`}
                  value={b.label}
                  maxLength={40}
                  onChange={(e) =>
                    update({ breaks: s.breaks.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })
                  }
                  className="w-32 rounded-md border border-slate-300 px-2 py-1 text-sm"
                />
                <button
                  type="button"
                  aria-label={`Remove break ${i + 1}`}
                  onClick={() => update({ breaks: s.breaks.filter((_, j) => j !== i) })}
                  className="text-slate-400 hover:text-red-600"
                >
                  ✕
                </button>
              </div>
            ))}
            {fullDay > 1 && (
              <button
                type="button"
                onClick={() => {
                  const used = new Set(s.breaks.map((b) => Number(b.after)))
                  const after = range(1, fullDay - 1).find((k) => !used.has(k) && k >= Math.ceil(fullDay / 2)) ??
                    range(1, fullDay - 1).find((k) => !used.has(k))
                  if (after != null) update({ breaks: [...s.breaks, { after, label: s.breaks.length ? 'Lunch' : 'Break' }] })
                }}
                className="w-fit text-xs font-medium text-slate-600 underline underline-offset-2"
              >
                + Add a break
              </button>
            )}
          </div>
        </Row>

        <Row
          label="Class teacher period"
          hint="Each section with its own class teacher - attendance and the like. Not counted towards anyone's weekly maximum."
        >
          <Toggle
            label="Class teacher period"
            on={s.class_teacher_period.enabled}
            onChange={(enabled) => update({ class_teacher_period: { ...s.class_teacher_period, enabled } })}
          />
          {s.class_teacher_period.enabled && (
            <select
              aria-label="When the class teacher period is"
              value={s.class_teacher_period.after}
              onChange={(e) => update({ class_teacher_period: { enabled: true, after: Number(e.target.value) } })}
              className="rounded-md border border-slate-300 px-1.5 py-1 text-sm"
            >
              <option value={0}>Start of the day</option>
              {range(1, fullDay - 1).map((k) => (
                <option key={k} value={k}>
                  After period {k}
                </option>
              ))}
            </select>
          )}
        </Row>

        <Row
          label="Zero period"
          hint="A free slot for activities - no lessons are timetabled in it, and it isn't counted towards anyone's weekly maximum."
        >
          <Toggle
            label="Zero period"
            on={s.zero_period.enabled}
            onChange={(enabled) =>
              update({
                zero_period: enabled
                  ? { enabled, scope: 'school', placements: [{ grade: null, every_day: 1, by_day: null }] }
                  : { ...s.zero_period, enabled },
              })
            }
          />
          {s.zero_period.enabled && <ZeroPeriodEditor s={s} grades={grades} update={update} />}
        </Row>
      </fieldset>

      <Preview s={s} />

      {error && <p className="text-sm text-red-600">{error}</p>}
      {report && <Report report={report} />}

      {!readOnly && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || s.days.length === 0 || !s.periods_per_day}
            className="rounded-md bg-neutral-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {saving ? 'Saving…' : hasPeriods ? 'Save changes' : 'Create periods'}
          </button>
          {hasPeriods && (
            <span className="text-xs text-slate-400">
              Existing periods are kept where they still fit, so rules and teacher availability stay put.
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function range(from, to) {
  const out = []
  for (let k = from; k <= to; k++) out.push(k)
  return out
}

function Row({ label, hint, children }) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-[180px_1fr] sm:gap-4">
      <div>
        <div className="text-sm font-medium text-slate-700">{label}</div>
        {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
      </div>
      <div className="flex flex-wrap items-start gap-3">{children}</div>
    </div>
  )
}

function Toggle({ label, on, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={`relative mt-0.5 inline-flex h-5 w-9 flex-none items-center rounded-full transition-colors ${
        on ? 'bg-neutral-900' : 'bg-slate-300'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
          on ? 'translate-x-4' : 'translate-x-0.5'
        }`}
      />
    </button>
  )
}

/** A day with fewer periods - a half-day Saturday, say. */
function ShortDays({ s, update }) {
  const n = Number(s.periods_per_day) || 1
  const entries = Object.entries(s.short_days).map(([d, k]) => [Number(d), Number(k)])
  const free = s.days.filter((d) => !(d in s.short_days))
  if (n < 2) return null
  return (
    <div className="flex flex-col gap-1.5">
      {entries.map(([d, k]) => (
        <div key={d} className="flex items-center gap-2 text-sm">
          <span className="text-slate-600">{DAY_FULL[d]}:</span>
          <select
            aria-label={`Periods on ${DAY_FULL[d]}`}
            value={k}
            onChange={(e) => update({ short_days: { ...s.short_days, [d]: Number(e.target.value) } })}
            className="rounded-md border border-slate-300 px-1.5 py-1 text-sm"
          >
            {range(1, n - 1).map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
          <span className="text-slate-500">periods</span>
          <button
            type="button"
            aria-label={`Make ${DAY_FULL[d]} a full day`}
            onClick={() => {
              const short_days = { ...s.short_days }
              delete short_days[d]
              update({ short_days })
            }}
            className="text-slate-400 hover:text-red-600"
          >
            ✕
          </button>
        </div>
      ))}
      {free.length > 0 && (
        <select
          aria-label="Add a shorter day"
          value=""
          onChange={(e) => {
            if (e.target.value === '') return
            update({ short_days: { ...s.short_days, [Number(e.target.value)]: Math.max(1, Math.min(n - 1, 4)) } })
          }}
          className="w-fit rounded-md border border-dashed border-slate-300 px-1.5 py-1 text-xs text-slate-600"
        >
          <option value="">+ A day with fewer periods…</option>
          {free.map((d) => (
            <option key={d} value={d}>
              {DAY_FULL[d]}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

/**
 * Where the zero period goes: for the whole school or per grade, and at one
 * point every day or a different point each day.
 */
function ZeroPeriodEditor({ s, grades, update }) {
  const z = s.zero_period
  const setZero = (patch) => update({ zero_period: { ...z, ...patch } })

  return (
    <div className="flex w-full flex-col gap-3 rounded-md border border-slate-200 p-3">
      <div className="flex flex-wrap gap-4 text-sm">
        {[
          ['school', 'Whole school'],
          ['grade', 'Different by grade'],
        ].map(([value, label]) => (
          <label key={value} className="flex items-center gap-1.5">
            <input
              type="radio"
              name="zero-scope"
              checked={z.scope === value}
              disabled={value === 'grade' && grades.length === 0}
              onChange={() =>
                setZero({
                  scope: value,
                  placements:
                    value === 'school'
                      ? [{ grade: null, every_day: 1, by_day: null }]
                      : grades.map((g) => ({ grade: g, every_day: 1, by_day: null })),
                })
              }
            />
            {label}
          </label>
        ))}
      </div>

      {z.scope === 'school' ? (
        <PlacementEditor
          s={s}
          placement={z.placements[0]}
          who="the whole school"
          onChange={(p) => setZero({ placements: [p] })}
        />
      ) : (
        <div className="flex flex-col gap-2">
          {grades.map((grade) => {
            const placement = z.placements.find((p) => p.grade === grade)
            return (
              <div key={grade} className="flex flex-wrap items-start gap-3 border-t border-slate-100 pt-2 first:border-0 first:pt-0">
                <label className="flex w-32 items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    checked={!!placement}
                    onChange={(e) =>
                      setZero({
                        placements: e.target.checked
                          ? [...z.placements, { grade, every_day: 1, by_day: null }]
                          : z.placements.filter((p) => p.grade !== grade),
                      })
                    }
                  />
                  {grade}
                </label>
                {placement && (
                  <PlacementEditor
                    s={s}
                    placement={placement}
                    who={grade}
                    onChange={(p) =>
                      setZero({ placements: z.placements.map((x) => (x.grade === grade ? p : x)) })
                    }
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function PlacementEditor({ s, placement, who, onChange }) {
  const eachDay = placement.by_day != null
  // Labels follow what the slot will be. A whole-school zero period at one
  // point every day has no number, so it falls "before period 3"; anywhere
  // else it is a numbered period of its own.
  const unnumbered = s.zero_period.scope === 'school' && !eachDay
  const slotLabel = (k, day) => {
    const full = (day == null ? Number(s.periods_per_day) : periodsOn(s, day)) || 1
    if (unnumbered) return k > full ? `After period ${full}` : `Before period ${k}`
    return `Period ${k}`
  }
  const options = (day) =>
    range(1, (day == null ? Number(s.periods_per_day) : periodsOn(s, day)) + 1).map((k) => (
      <option key={k} value={k}>
        {slotLabel(k, day)}
      </option>
    ))

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-1.5">
          <input
            type="radio"
            checked={!eachDay}
            onChange={() => onChange({ ...placement, every_day: 1, by_day: null })}
            aria-label={`Same time every day for ${who}`}
          />
          Same every day
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="radio"
            checked={eachDay}
            onChange={() =>
              onChange({ ...placement, every_day: null, by_day: Object.fromEntries(s.days.map((d) => [d, 1])) })
            }
            aria-label={`Different each day for ${who}`}
          />
          Different each day
        </label>
      </div>
      {!eachDay ? (
        <select
          aria-label={`Zero period for ${who}`}
          value={placement.every_day ?? 1}
          onChange={(e) => onChange({ ...placement, every_day: Number(e.target.value) })}
          className="w-fit rounded-md border border-slate-300 px-1.5 py-1"
        >
          {options(null)}
        </select>
      ) : (
        <div className="flex flex-wrap gap-2">
          {s.days.map((d) => (
            <label key={d} className="flex items-center gap-1 text-xs text-slate-600">
              {DAY_SHORT[d]}
              <select
                aria-label={`Zero period for ${who} on ${DAY_FULL[d]}`}
                value={placement.by_day?.[d] ?? ''}
                onChange={(e) => {
                  const by_day = { ...placement.by_day }
                  if (e.target.value === '') delete by_day[d]
                  else by_day[d] = Number(e.target.value)
                  onChange({ ...placement, by_day })
                }}
                className="rounded-md border border-slate-300 px-1 py-0.5 text-xs"
              >
                <option value="">None</option>
                {options(d)}
              </select>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

const CHIP = {
  lesson: 'border-slate-300 bg-white text-slate-700',
  break: 'border-amber-200 bg-amber-50 text-amber-800',
  class_teacher: 'border-violet-200 bg-violet-50 text-violet-800',
  zero: 'border-emerald-200 bg-emerald-50 text-emerald-800',
}

/** What the days will look like - grouped, since most days are the same. */
function Preview({ s }) {
  if (s.days.length === 0 || !s.periods_per_day) return null
  const groups = []
  for (const d of s.days) {
    const slots = layoutDay(s, d)
    const key = JSON.stringify(slots)
    const same = groups.find((g) => g.key === key)
    if (same) same.days.push(d)
    else groups.push({ key, days: [d], slots })
  }
  return (
    <div className="flex flex-col gap-2 rounded-md bg-slate-50 p-3" aria-label="Preview of the day">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Preview</div>
      {groups.map((g) => (
        <div key={g.key} className="flex flex-wrap items-center gap-1.5">
          <span className="w-24 text-xs text-slate-500">{g.days.map((d) => DAY_SHORT[d]).join(', ')}</span>
          {g.slots.map((slot, i) => (
            <span
              key={i}
              title={slot.zeroFor?.length ? `Zero period for ${slot.zeroFor.join(', ')}` : undefined}
              className={`rounded border px-1.5 py-0.5 text-xs ${CHIP[slot.kind]} ${
                slot.zeroFor?.length ? 'ring-2 ring-emerald-300' : ''
              }`}
            >
              {slot.kind === 'lesson'
                ? slot.number
                : slot.kind === 'break'
                ? slot.label
                : slot.kind === 'class_teacher'
                ? 'Class teacher'
                : 'Zero'}
            </span>
          ))}
        </div>
      ))}
      {zeroIsNumbered(s) && (
        <p className="text-xs text-slate-500">
          Ringed periods are a zero period - kept free for{' '}
          {s.zero_period.scope === 'school' ? 'everyone' : 'that grade, and taught as usual for the others'}.
          The day gains a period for it, so sections still get {s.periods_per_day} lessons.
        </p>
      )}
    </div>
  )
}

function Report({ report }) {
  const notes = []
  if (!report.changed) notes.push('Nothing needed to change.')
  if (report.periods_added || report.periods_removed) {
    notes.push(
      `${report.periods_added} period${report.periods_added === 1 ? '' : 's'} added, ` +
        `${report.periods_removed} removed.`,
    )
  }
  if (report.timetable_entries_removed) {
    notes.push(`${report.timetable_entries_removed} lessons were in periods that no longer exist.`)
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
      <span className="font-medium">Saved.</span>
      {notes.map((n) => (
        <span key={n}>{n}</span>
      ))}
      {report.timetable_outdated && (
        <span className="text-amber-800">
          Your timetable was made for the old structure - generate it again to use this one.
        </span>
      )}
      {report.unavailability_removed.map((n) => (
        <span key={n} className="text-amber-800">
          {n}.
        </span>
      ))}
      {report.rules_out_of_range.map((n) => (
        <span key={n} className="text-amber-800">
          {n}
        </span>
      ))}
      {report.sections_without_class_teacher.length > 0 && (
        <span className="text-amber-800">
          No class teacher yet for {report.sections_without_class_teacher.join(', ')} - set one on each
          section's plan.
        </span>
      )}
    </div>
  )
}
