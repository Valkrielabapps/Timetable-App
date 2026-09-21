import { useState } from 'react'

/**
 * CRUD panel for a school's rooms. Optional — a school with no rooms
 * entered just gets no room assigned on generated timetables (room_id
 * stays null), same as before this feature existed. Once rooms exist,
 * the solver (see backend/app/services/solver.py) tries to assign one to
 * every scheduled period, matching a subject's `required_room_type` (set
 * per-subject in the Subjects table) and each room's `capacity` against
 * the class group's `student_count` where those are set.
 *
 * `rooms` and the `onCreate`/`onDelete` callbacks are owned by the parent
 * (DataEntryTab, backed by App.jsx's lifted state) rather than fetched
 * independently here — same reasoning as PeriodsPanel: rooms are already
 * loaded school-wide, so a second independent fetch on mount was pure
 * extra latency for data the app already had.
 */
export default function RoomsPanel({ schoolId, rooms, onCreate, onDelete, readOnly = false }) {
  const [name, setName] = useState('')
  const [capacity, setCapacity] = useState('')
  const [roomType, setRoomType] = useState('')
  const [error, setError] = useState(null)

  async function handleAdd(e) {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await onCreate({
        school_id: schoolId,
        name: name.trim(),
        capacity: capacity === '' ? null : Number(capacity),
        room_type: roomType.trim() || null,
      })
      setName('')
      setCapacity('')
      setRoomType('')
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
      <h2 className="mb-4 text-lg font-medium">Rooms</h2>
      <p className="mb-4 text-sm text-slate-500">
        Optional. Add rooms if you want the generated timetable to assign
        one per period — e.g. matching "Chemistry" (room type "lab" set on
        the subject) to a room typed "lab" here. Leave this empty and room
        assignment is simply skipped.
      </p>

      {!readOnly && (
        <form onSubmit={handleAdd} className="mb-4 flex flex-wrap gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Room name (e.g. Lab 1)"
            className="flex-1 min-w-[160px] rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <input
            value={capacity}
            onChange={(e) => setCapacity(e.target.value)}
            type="number"
            min="0"
            placeholder="Capacity"
            className="w-28 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <input
            value={roomType}
            onChange={(e) => setRoomType(e.target.value)}
            placeholder="Type (e.g. lab, regular)"
            className="w-44 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <button className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700">
            Add
          </button>
        </form>
      )}

      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      <ul className="divide-y divide-slate-200">
        {rooms.map((r) => (
          <li key={r.id} className="flex items-center justify-between py-2 text-sm">
            <span>
              {r.name}
              {r.room_type ? ` · ${r.room_type}` : ''}
              {r.capacity ? ` · capacity ${r.capacity}` : ''}
            </span>
            {!readOnly && (
              <button
                onClick={() => handleDelete(r.id)}
                className="text-xs text-slate-400 hover:text-red-600"
              >
                Remove
              </button>
            )}
          </li>
        ))}
        {rooms.length === 0 && <p className="py-2 text-sm text-slate-500">No rooms yet.</p>}
      </ul>
    </div>
  )
}
