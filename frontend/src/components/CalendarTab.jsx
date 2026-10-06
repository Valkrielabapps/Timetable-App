import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { useTimetable, useTimetables } from '../hooks/useSchoolData'

/**
 * Calendar: the generated timetable laid out against real dates.
 *
 * A timetable here is a weekly pattern (Monday period 3, Tuesday period 1,
 * ...), not a list of dated lessons, so any date simply shows its weekday's
 * pattern. That means:
 *   - Day view: a grid with the day's periods down the side and one column
 *     per teacher, class or room (toggle at the top right).
 *   - Month view: a month grid; each day shows how many lessons run that
 *     weekday, and clicking a day opens it in Day view.
 *   - A weekday with no periods (usually Sunday) reads "No lessons
 *     scheduled for this day."
 * Holidays and leave aren't modelled yet, so they don't appear here.
 *
 * Reads the most recent finished timetable (draft or published) through the
 * same React Query cache as the Timetable tab, so it costs no extra request
 * when that tab has already loaded.
 */

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const WEEKDAY_HEADERS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// Literal class strings so Tailwind keeps them.
const SUBJECT_TINTS = [
  'bg-indigo-50 text-indigo-800 border-indigo-100',
  'bg-emerald-50 text-emerald-800 border-emerald-100',
  'bg-amber-50 text-amber-800 border-amber-100',
  'bg-sky-50 text-sky-800 border-sky-100',
  'bg-rose-50 text-rose-800 border-rose-100',
  'bg-violet-50 text-violet-800 border-violet-100',
  'bg-teal-50 text-teal-800 border-teal-100',
  'bg-orange-50 text-orange-800 border-orange-100',
]

const pad = (n) => String(n).padStart(2, '0')
const toInputValue = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const fromInputValue = (v) => {
  const [y, m, d] = v.split('-').map(Number)
  return new Date(y, m - 1, d)
}
// JS getDay() is Sunday=0; the backend counts Monday=0.
const weekdayIndex = (d) => (d.getDay() + 6) % 7
const sameDay = (a, b) => toInputValue(a) === toInputValue(b)
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
const addMonths = (d, n) => new Date(d.getFullYear(), d.getMonth() + n, 1)

export default function CalendarTab({ schoolId, periods, teachers, classGroups, onNavigate, initialDate }) {
  const [date, setDate] = useState(() => initialDate || new Date())
  const [mode, setMode] = useState('day') // 'day' | 'month'
  const [view, setView] = useState('teachers') // 'teachers' | 'classes' | 'rooms'

  const { data: list = [], isLoading: listLoading } = useTimetables(schoolId)
  const finished = list.filter((t) => t.status === 'draft' || t.status === 'published')
  const timetableId = finished.length > 0 ? finished.reduce((a, b) => (b.id > a.id ? b : a)).id : null
  const { data: timetable, isLoading: timetableLoading } = useTimetable(timetableId)
  const entries = timetable?.entries ?? []

  const entriesByWeekday = useMemo(() => {
    const map = Array.from({ length: 7 }, () => [])
    for (const e of entries) if (e.day_of_week >= 0 && e.day_of_week < 7) map[e.day_of_week].push(e)
    return map
  }, [entries])

  const periodsByWeekday = useMemo(() => {
    const map = Array.from({ length: 7 }, () => [])
    for (const p of periods) if (p.day_of_week >= 0 && p.day_of_week < 7) map[p.day_of_week].push(p)
    for (const day of map) day.sort((a, b) => a.order - b.order)
    return map
  }, [periods])

  const today = new Date()
  const loading = listLoading || (timetableId != null && timetableLoading)

  function step(direction) {
    setDate((d) => (mode === 'month' ? addMonths(d, direction) : addDays(d, direction)))
  }

  const subtitle =
    mode === 'month'
      ? date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
      : date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })

  return (
    <div className="flex max-w-full flex-col gap-4">
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="text-neutral-900" aria-hidden="true">
              <rect x="3" y="5" width="18" height="16" rx="2.5" />
              <path d="M8 3v4M16 3v4M3 10h18" />
            </svg>
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Calendar</h2>
              <p className="text-sm text-slate-500">{subtitle}</p>
            </div>
          </div>
          {timetableId != null && <ExportMenu timetableId={timetableId} />}
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <IconButton label={mode === 'month' ? 'Previous month' : 'Previous day'} onClick={() => step(-1)}>
              <path d="m15 18-6-6 6-6" />
            </IconButton>
            <input
              type="date"
              aria-label="Choose a date"
              value={toInputValue(date)}
              onChange={(e) => e.target.value && setDate(fromInputValue(e.target.value))}
              className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm focus:border-neutral-900 focus:outline-none"
            />
            <IconButton label={mode === 'month' ? 'Next month' : 'Next day'} onClick={() => step(1)}>
              <path d="m9 18 6-6-6-6" />
            </IconButton>
            <button
              onClick={() => setDate(new Date())}
              className="h-10 rounded-lg border border-slate-300 px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Today
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Segmented
              label="Calendar range"
              value={mode}
              onChange={setMode}
              options={[
                { value: 'month', label: 'Month' },
                { value: 'day', label: 'Day' },
              ]}
            />
            {mode === 'day' && (
              <Segmented
                label="Group by"
                value={view}
                onChange={setView}
                options={[
                  { value: 'teachers', label: 'Teachers' },
                  { value: 'classes', label: 'Classes' },
                  { value: 'rooms', label: 'Rooms' },
                ]}
              />
            )}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white">
        {loading ? (
          <p className="px-6 py-16 text-center text-sm text-slate-400">Loading…</p>
        ) : timetableId == null ? (
          <EmptyState
            title="No timetable yet"
            body="Generate a timetable and it will show up here, day by day."
            action={onNavigate && { label: 'Go to Timetable', onClick: () => onNavigate('timetable') }}
          />
        ) : mode === 'month' ? (
          <MonthGrid
            date={date}
            today={today}
            entriesByWeekday={entriesByWeekday}
            periodsByWeekday={periodsByWeekday}
            onPick={(d) => {
              setDate(d)
              setMode('day')
            }}
          />
        ) : (
          <DayGrid
            weekday={weekdayIndex(date)}
            date={date}
            view={view}
            entries={entriesByWeekday[weekdayIndex(date)]}
            periods={periodsByWeekday[weekdayIndex(date)]}
            teachers={teachers}
            classGroups={classGroups}
            allEntries={entries}
          />
        )}
      </div>
    </div>
  )
}

function IconButton({ label, onClick, children }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-50"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {children}
      </svg>
    </button>
  )
}

function Segmented({ label, value, onChange, options }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1 text-sm">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={`rounded-md px-3.5 py-1.5 font-medium ${
            value === o.value ? 'bg-white text-neutral-900 shadow-sm ring-1 ring-slate-200' : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function EmptyState({ title, body, subtle, action }) {
  return (
    <div className="flex flex-col items-center px-6 py-16 text-center">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-300" aria-hidden="true">
        <rect x="3" y="5" width="18" height="16" rx="3" />
        <path d="M8 3v4M16 3v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />
      </svg>
      <h3 className="mt-5 text-lg font-semibold">{title}</h3>
      <p className="mt-1.5 text-sm text-slate-500">{body}</p>
      {subtle && <p className="mt-1 text-xs text-slate-400">{subtle}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-5 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

function ExportMenu({ timetableId }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  async function run(format) {
    setBusy(format)
    setError(null)
    try {
      await api.downloadTimetableExport(timetableId, format)
      setOpen(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex h-10 items-center gap-2 rounded-lg bg-neutral-900 px-4 text-sm font-medium text-white hover:bg-neutral-700"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
        </svg>
        Export
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-44 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          {[
            ['xlsx', 'Excel (.xlsx)'],
            ['pdf', 'PDF'],
          ].map(([format, label]) => (
            <button
              key={format}
              onClick={() => run(format)}
              disabled={busy != null}
              className="w-full rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {busy === format ? 'Preparing…' : label}
            </button>
          ))}
          {error && <p className="px-3 py-2 text-xs text-red-600">{error}</p>}
        </div>
      )}
    </div>
  )
}

function MonthGrid({ date, today, entriesByWeekday, periodsByWeekday, onPick }) {
  const first = new Date(date.getFullYear(), date.getMonth(), 1)
  const daysInMonth = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate()
  const leading = weekdayIndex(first)
  const cells = [
    ...Array.from({ length: leading }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(date.getFullYear(), date.getMonth(), i + 1)),
  ]
  while (cells.length % 7 !== 0) cells.push(null)

  return (
    <div className="p-4">
      <div className="grid grid-cols-7 gap-px text-center text-xs font-medium uppercase tracking-wide text-slate-400">
        {WEEKDAY_HEADERS.map((d) => (
          <div key={d} className="pb-2">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {cells.map((d, i) => {
          if (!d) return <div key={`blank-${i}`} className="min-h-[84px]" />
          const wd = weekdayIndex(d)
          const teaching = periodsByWeekday[wd].filter((p) => !p.is_break).length
          const lessons = entriesByWeekday[wd].length
          const isToday = sameDay(d, today)
          const isSelected = sameDay(d, date)
          return (
            <button
              key={toInputValue(d)}
              data-date={toInputValue(d)}
              onClick={() => onPick(d)}
              aria-label={d.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
              className={`flex min-h-[84px] flex-col items-start rounded-lg border p-2 text-left transition-colors hover:border-slate-400 ${
                isSelected ? 'border-neutral-900 bg-neutral-50' : 'border-slate-200 bg-white'
              } ${teaching === 0 ? 'bg-slate-50/70' : ''}`}
            >
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full text-sm font-medium ${
                  isToday ? 'bg-neutral-900 text-white' : teaching === 0 ? 'text-slate-400' : 'text-slate-800'
                }`}
              >
                {d.getDate()}
              </span>
              <span className="mt-auto text-[11px] leading-tight text-slate-500">
                {teaching === 0 ? 'No school' : `${teaching} periods`}
                {teaching > 0 && <span className="block text-slate-400">{lessons} lessons</span>}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function DayGrid({ weekday, date, view, entries, periods, teachers, classGroups, allEntries }) {
  const dayLabel = DAY_NAMES[weekday]
  const longDate = date.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

  const { columns, cellFor } = useMemo(() => {
    const classNames = new Map()
    for (const e of allEntries) classNames.set(e.class_group_id, e.class_group_name)

    let cols = []
    let place = () => []
    if (view === 'teachers') {
      const known = new Map(teachers.map((t) => [t.id, t.name]))
      for (const e of allEntries) {
        if (!known.has(e.teacher_id)) known.set(e.teacher_id, e.teacher_name)
        if (e.assistant_teacher_id && !known.has(e.assistant_teacher_id)) known.set(e.assistant_teacher_id, e.assistant_teacher_name)
      }
      cols = [...known].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
      place = (e) => {
        const out = [[e.teacher_id, { primary: `${e.subject_name}`, secondary: [e.class_group_name, e.room_name].filter(Boolean).join(' · ') }]]
        if (e.assistant_teacher_id) {
          out.push([e.assistant_teacher_id, { primary: e.subject_name, secondary: `${e.class_group_name} · assisting` }])
        }
        return out
      }
    } else if (view === 'classes') {
      cols = classGroups
        .map((cg) => ({ id: cg.id, name: classNames.get(cg.id) || [cg.grade, cg.name].filter(Boolean).join(' - ') }))
        .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
      place = (e) => [[e.class_group_id, {
        primary: e.subject_name,
        secondary: [e.teacher_name, e.room_name, e.lab_batch ? `Batch ${e.lab_batch}` : null].filter(Boolean).join(' · '),
      }]]
    } else {
      const rooms = new Map()
      for (const e of allEntries) if (e.room_id != null) rooms.set(e.room_id, e.room_name)
      cols = [...rooms].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
      place = (e) => (e.room_id == null ? [] : [[e.room_id, { primary: e.subject_name, secondary: [e.class_group_name, e.teacher_name].filter(Boolean).join(' · ') }]])
    }

    const byKey = new Map()
    for (const e of entries) {
      for (const [colId, text] of place(e)) {
        const key = `${colId}:${e.period_id}`
        if (!byKey.has(key)) byKey.set(key, [])
        byKey.get(key).push({ ...text, subjectId: e.subject_id, id: e.id })
      }
    }
    return { columns: cols, cellFor: (colId, periodId) => byKey.get(`${colId}:${periodId}`) || [] }
  }, [view, entries, allEntries, teachers, classGroups])

  if (periods.length === 0) {
    return (
      <EmptyState
        title="No Schedule Available"
        body="No lessons scheduled for this day."
        subtle={`Selected date: ${longDate}`}
      />
    )
  }

  if (columns.length === 0) {
    return (
      <EmptyState
        title={view === 'rooms' ? 'No rooms used' : 'Nothing to show'}
        body={view === 'rooms' ? 'None of the lessons in this timetable have a room assigned.' : 'Add teachers and classes to see them here.'}
      />
    )
  }

  const noun = view === 'teachers' ? 'Teacher' : view === 'classes' ? 'Class' : 'Room'

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-sm">
        <caption className="sr-only">
          {dayLabel} timetable by {noun.toLowerCase()}
        </caption>
        <thead>
          <tr>
            <th className="sticky left-0 z-10 w-28 min-w-[112px] border-b border-r border-slate-200 bg-slate-50 px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
              {dayLabel}
            </th>
            {columns.map((c) => (
              <th key={c.id} scope="col" className="min-w-[150px] border-b border-slate-200 bg-slate-50 px-3 py-2.5 text-left text-xs font-semibold text-slate-700">
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {periods.map((p) =>
            p.is_break ? (
              <tr key={p.id}>
                <th scope="row" className="sticky left-0 z-10 border-b border-r border-slate-200 bg-slate-50 px-3 py-1.5 text-left text-xs font-medium text-slate-400">
                  {p.label || 'Break'}
                </th>
                <td colSpan={columns.length} className="border-b border-slate-200 bg-slate-50/60 px-3 py-1.5 text-center text-xs text-slate-400">
                  Break
                </td>
              </tr>
            ) : (
              <tr key={p.id}>
                <th scope="row" className="sticky left-0 z-10 border-b border-r border-slate-200 bg-white px-3 py-3 text-left align-top text-xs font-medium text-slate-600">
                  {p.label || `Period ${p.order}`}
                </th>
                {columns.map((c) => {
                  const items = cellFor(c.id, p.id)
                  return (
                    <td key={c.id} className="border-b border-slate-100 p-1.5 align-top">
                      {items.map((it) => (
                        <div
                          key={`${it.id}-${c.id}`}
                          className={`mb-1 rounded-md border px-2 py-1.5 last:mb-0 ${SUBJECT_TINTS[(it.subjectId ?? 0) % SUBJECT_TINTS.length]}`}
                        >
                          <p className="text-[13px] font-medium leading-tight">{it.primary}</p>
                          {it.secondary && <p className="mt-0.5 text-[11px] leading-tight opacity-75">{it.secondary}</p>}
                        </div>
                      ))}
                    </td>
                  )
                })}
              </tr>
            )
          )}
        </tbody>
      </table>
    </div>
  )
}
