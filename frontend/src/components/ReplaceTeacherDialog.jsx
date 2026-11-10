import { useMemo, useState } from 'react'
import { api } from '../api'

/**
 * "Ravi instead of Anil": the plan changes, and in the timetable Ravi takes
 * each of Anil's lessons where he is free - at once, nothing else moves.
 * Lessons at times Ravi already teaches are offered as an update, which
 * places just those (backend app/services/adjust.py).
 */
export default function ReplaceTeacherDialog({ schoolId, teachers, classGroups, entries, onClose, onDone, onUpdate }) {
  const [fromId, setFromId] = useState('')
  const [toId, setToId] = useState('')
  const [scope, setScope] = useState('all')
  const [picked, setPicked] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const name = (id) => teachers.find((t) => t.id === Number(id))?.name ?? ''
  // The sections the leaving teacher teaches, to choose from.
  const theirSections = useMemo(() => {
    const ids = new Set(entries.filter((e) => e.teacher_id === Number(fromId)).map((e) => e.class_group_id))
    return classGroups.filter((c) => ids.has(c.id))
  }, [entries, fromId, classGroups])
  const lessons = entries.filter((e) => e.teacher_id === Number(fromId)).length

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await api.replaceTeacher({
        school_id: schoolId,
        from_teacher_id: Number(fromId),
        to_teacher_id: Number(toId),
        class_group_ids: scope === 'some' ? picked : null,
      })
      setResult(res)
      onDone?.(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Replace a teacher" className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-5 text-sm shadow-xl">
        <h2 className="text-base font-semibold">Replace a teacher</h2>
        <p className="mt-1 text-slate-600">
          For when a teacher leaves or hands over a class. The new teacher takes their lessons at the same times wherever
          they&rsquo;re free; nothing else in the timetable moves.
        </p>

        {result ? (
          <div className="mt-4 flex flex-col gap-3">
            <p className="rounded-md bg-emerald-50 px-3 py-2 text-emerald-900" role="status">
              {name(toId)} took {result.swapped} of {name(fromId)}&rsquo;s lessons at the same times
              {result.plan > 0 && ', and the plan now names them'}.
            </p>
            {result.left > 0 ? (
              <>
                <p className="text-amber-900">
                  {result.left} {result.left === 1 ? 'lesson is at a time' : 'lessons are at times'} {name(toId)} already
                  teaches. Update the timetable to place {result.left === 1 ? 'it' : 'them'}; everything else stays where it is.
                </p>
                <div className="flex gap-2">
                  <button type="button" className="tw-btn tw-primary" onClick={onUpdate}>Update the timetable</button>
                  <button type="button" className="tw-btn" onClick={onClose}>Later</button>
                </div>
              </>
            ) : (
              <button type="button" className="tw-btn tw-primary w-fit" onClick={onClose}>Done</button>
            )}
          </div>
        ) : (
          <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-500">Replace</span>
              <select className="tw-btn" value={fromId} onChange={(e) => { setFromId(e.target.value); setPicked([]) }}>
                <option value="">Choose a teacher</option>
                {teachers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              {fromId && <span className="text-xs text-slate-500">{lessons} lessons a week in this timetable</span>}
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-500">With</span>
              <select className="tw-btn" value={toId} onChange={(e) => setToId(e.target.value)}>
                <option value="">Choose a teacher</option>
                {teachers.filter((t) => String(t.id) !== fromId).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
            {fromId && theirSections.length > 1 && (
              <fieldset className="flex flex-col gap-1">
                <legend className="text-xs font-medium text-slate-500">Where</legend>
                <label className="flex items-center gap-2">
                  <input type="radio" checked={scope === 'all'} onChange={() => setScope('all')} /> Everywhere
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" checked={scope === 'some'} onChange={() => setScope('some')} /> Only some sections
                </label>
                {scope === 'some' && (
                  <div className="ml-6 flex flex-wrap gap-x-3 gap-y-1">
                    {theirSections.map((c) => (
                      <label key={c.id} className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={picked.includes(c.id)}
                          onChange={(e) => setPicked((p) => (e.target.checked ? [...p, c.id] : p.filter((x) => x !== c.id)))}
                        />
                        {c.grade ? `${c.grade} ${c.name}` : c.name}
                      </label>
                    ))}
                  </div>
                )}
              </fieldset>
            )}
            {error && <p className="text-red-600">{error}</p>}
            <div className="flex gap-2">
              <button
                className="tw-btn tw-primary"
                disabled={busy || !fromId || !toId || (scope === 'some' && picked.length === 0)}
              >
                {busy ? 'Replacing…' : 'Replace'}
              </button>
              <button type="button" className="tw-btn" onClick={onClose}>Cancel</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
