import { useState } from 'react'

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

/**
 * CRUD panel for a school's periods (schedulable time slots). The solver
 * treats these as the units it assigns subjects into, so a school needs at
 * least as many periods as the sum of its weekly subject requirements
 * before generation can succeed.
 *
 * A period can be marked as a *break* (lunch, assembly). It still occupies
 * a slot in the day - so "the period after lunch" refers to something, and
 * so a teacher's back-to-back run is correctly interrupted by it - but the
 * solver never schedules into one, and the constraint parser is told it
 * exists so rules phrased around it can resolve.
 *
 * `periods` and the `onCreate`/`onDelete`/`onUpdate` callbacks are owned by the
 * parent (DataEntryTab, backed by App.jsx's lifted state) rather than
 * fetched independently here — periods are already loaded school-wide by
 * the time this panel mounts, so an independent fetch-on-mount was a pure
 * extra round trip (and the visible cause of a beat of blank/stale periods
 * every time the Setup page was opened) for data the app already had.
 */
export default function PeriodsPanel({ schoolId, periods, onCreate, onDelete, onUpdate, readOnly = false }) {
  const [dayOfWeek, setDayOfWeek] = useState(0)
  const [order, setOrder] = useState('')
  const [label, setLabel] = useState('')
  const [isBreak, setIsBreak] = useState(false)
  const [error, setError] = useState(null)

  async function handleAdd(e) {
    e.preventDefault()
    if (order === '') return
    try {
      await onCreate({
        school_id: schoolId,
        day_of_week: Number(dayOfWeek),
        order: Number(order),
        label: label.trim() || null,
        is_break: isBreak,
      })
      setOrder('')
      setLabel('')
      setIsBreak(false)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleToggleBreak(period) {
    try {
      await onUpdate(period.id, { is_break: !period.is_break })
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(id) {
    try {
      await onDelete(id)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2 className="mb-4 text-lg font-medium">Periods</h2>
      <p className="mb-4 text-sm text-slate-500">
        Each row is one slot in the day, e.g. "Monday, period 1". Add every
        slot the school actually teaches in. Mark lunch, assembly or games as a{' '}
        <span className="font-medium text-amber-700">break</span> — nothing is
        scheduled into one, but it still separates the periods either side of
        it, so rules like "no PE right after lunch" work.
      </p>

      {!readOnly && (
        <form onSubmit={handleAdd} className="mb-4 flex flex-wrap gap-2">
          <select
            value={dayOfWeek}
            onChange={(e) => setDayOfWeek(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
          >
            {DAY_NAMES.map((d, i) => (
              <option key={i} value={i}>
                {d}
              </option>
            ))}
          </select>
          <input
            value={order}
            onChange={(e) => setOrder(e.target.value)}
            placeholder="Order (1, 2, 3…)"
            type="number"
            className="w-36 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={isBreak ? 'Label (e.g. Lunch)' : 'Label (e.g. 9:00-9:45)'}
            className="flex-1 min-w-[160px] rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <label className="flex cursor-pointer items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">
            <input
              type="checkbox"
              checked={isBreak}
              onChange={(e) => setIsBreak(e.target.checked)}
              className="h-4 w-4 accent-amber-600"
            />
            Break
          </label>
          <button className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700">
            Add
          </button>
        </form>
      )}

      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      <ul className="divide-y divide-slate-200">
        {periods.map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
            <span className={p.is_break ? 'text-amber-700' : undefined}>
              {DAY_NAMES[p.day_of_week]} · #{p.order}
              {p.label ? ` · ${p.label}` : ''}
              {p.is_break && (
                <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                  Break
                </span>
              )}
            </span>
            {!readOnly && (
              <span className="flex flex-none items-center gap-3">
                <button
                  onClick={() => handleToggleBreak(p)}
                  className="text-xs text-slate-400 hover:text-amber-700"
                >
                  {p.is_break ? 'Mark as teaching' : 'Mark as break'}
                </button>
                <button
                  onClick={() => handleDelete(p.id)}
                  className="text-xs text-slate-400 hover:text-red-600"
                >
                  Remove
                </button>
              </span>
            )}
          </li>
        ))}
        {periods.length === 0 && (
          <p className="py-2 text-sm text-slate-500">No periods yet.</p>
        )}
      </ul>
    </div>
  )
}
