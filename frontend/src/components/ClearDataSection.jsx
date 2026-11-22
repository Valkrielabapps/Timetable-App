import { useState } from 'react'
import { api } from '../api'

/**
 * Settings > Clear all data: start the school over. Every section, teacher,
 * subject, class plan, rule, period, room, timetable and short form is
 * deleted; the school, its members, plan and invoices stay. The school's
 * name has to be typed first (backend: POST /schools/{id}/clear-data).
 */
export default function ClearDataSection({ school, isAdmin, onCleared }) {
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const matches = typed.trim().replace(/\s+/g, ' ').toLowerCase() === school.name.trim().replace(/\s+/g, ' ').toLowerCase()

  async function clear() {
    setBusy(true)
    setError(null)
    try {
      await api.clearSchoolData(school.id, typed)
      setOpen(false)
      setTyped('')
      await (onCleared ? onCleared() : window.location.reload())
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-lg border border-red-200 bg-white p-6">
      <h3 className="text-base font-semibold text-red-700">Clear all data</h3>
      <p className="mt-1 text-sm text-slate-600">
        Start this school over. Every section, teacher, subject, class plan, block, rule, period, room and timetable
        is deleted, along with the short forms it learned. The school itself, its members, its plan and invoices stay,
        so you can set it up again or import last year’s timetable afresh.
      </p>
      <p className="mt-2 text-sm font-medium text-slate-700">This can’t be undone.</p>
      {!isAdmin ? (
        <p className="mt-3 text-sm text-slate-500">Only an admin of this school can clear its data.</p>
      ) : !open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-4 rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
        >
          Clear all data…
        </button>
      ) : (
        <div className="mt-4 flex flex-col gap-2 rounded-md bg-red-50 p-4">
          <label htmlFor="clear-confirm" className="text-sm text-red-900">
            To confirm, type the school’s name: <strong>{school.name}</strong>
          </label>
          <input
            id="clear-confirm"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            className="rounded-md border border-red-300 bg-white px-3 py-2 text-sm"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={clear}
              disabled={!matches || busy}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {busy ? 'Clearing…' : 'Delete all of this school’s data'}
            </button>
            <button
              type="button"
              onClick={() => { setOpen(false); setTyped(''); setError(null) }}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </div>
      )}
    </section>
  )
}
