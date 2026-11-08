import { useEffect, useState } from 'react'
import { api } from '../api'

/**
 * Admin page: what a school has entered (backend GET /api/admin/schools/{id}/data),
 * and the type-the-name-to-confirm box every permanent delete goes through.
 */

export function DeleteBox({ what, confirmText, note, extra, onDelete, onCancel }) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const ok = typed.trim().toLowerCase() === confirmText.trim().toLowerCase()
  return (
    <form
      aria-label={`Delete ${what}`}
      className="flex flex-col gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setErr(null)
        try {
          await onDelete(typed)
        } catch (error) {
          setErr(error.message)
          setBusy(false)
        }
      }}
    >
      <p className="font-semibold text-red-800">Delete {what} for good?</p>
      <p className="text-red-800">{note} This can’t be undone.</p>
      {extra}
      <label className="flex flex-col gap-1 text-xs text-red-800">
        Type <span className="font-mono font-semibold">{confirmText}</span> to confirm
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          aria-label={`Type ${confirmText} to confirm`}
          className="rounded-md border border-red-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-red-600 focus:outline-none"
        />
      </label>
      {err && <p className="text-red-700">{err}</p>}
      <div className="flex gap-2">
        <button
          disabled={!ok || busy}
          className="rounded-md bg-red-600 px-3 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          {busy ? 'Deleting…' : `Delete ${what}`}
        </button>
        <button type="button" onClick={onCancel} className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium hover:bg-slate-50">
          Cancel
        </button>
      </div>
    </form>
  )
}

function Table({ title, cols, rows }) {
  const [open, setOpen] = useState(false)
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium"
      >
        {title} <span className="text-slate-500">{rows.length}</span>
      </button>
      {open && (
        <div className="max-h-80 overflow-auto border-t border-slate-100">
          {rows.length === 0 ? (
            <p className="px-4 py-3 text-xs text-slate-500">None.</p>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-50 text-slate-500">
                <tr>{cols.map(([label]) => <th key={label} className="px-4 py-2 font-medium">{label}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-t border-slate-100 align-top">
                    {cols.map(([label, get]) => <td key={label} className="px-4 py-1.5">{get(r) ?? '-'}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  )
}

export function SchoolData({ school }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    api.admin.schoolData(school.id).then(setData).catch((e) => setErr(e.message))
  }, [school.id])
  if (err) return <p className="text-sm text-red-600">{err}</p>
  if (!data) return <p className="text-sm text-slate-500">Loading the school’s data…</p>
  const subj = Object.fromEntries((data.subjects || []).map((s) => [s.id, s.name]))
  const sec = Object.fromEntries((data.class_groups || []).map((c) => [c.id, `${c.grade ?? ''} ${c.name}`.trim()]))
  const tch = Object.fromEntries((data.teachers || []).map((t) => [t.id, t.name]))
  const c = data.counts
  return (
    <div className="flex flex-col gap-2" aria-label={`${school.name} data`}>
      <p className="text-xs text-slate-600">
        {c.sections} sections · {c.subjects} subjects · {c.teachers} teachers · {c.rooms} rooms · {c.rules} rules ·{' '}
        {c.timetables} timetables · {c.people} people
      </p>
      <Table title="People" rows={data.people} cols={[['Email', (r) => r.email], ['Name', (r) => r.name], ['Role', (r) => r.role]]} />
      <Table title="Sections" rows={data.class_groups} cols={[['Section', (r) => sec[r.id]], ['Students', (r) => r.student_count], ['Class teacher', (r) => tch[r.class_teacher_id]]]} />
      <Table title="Subjects" rows={data.subjects} cols={[['Name', (r) => r.name], ['Room type', (r) => r.required_room_type]]} />
      <Table
        title="Teachers"
        rows={data.teachers}
        cols={[
          ['Name', (r) => r.name],
          ['Email', (r) => r.email],
          ['Subjects', (r) => (r.qualified_subject_ids || []).map((id) => subj[id]).filter(Boolean).join(', ')],
          ['Grades', (r) => (r.qualified_grades?.length ? r.qualified_grades.join(', ') : 'All')],
          ['Max / week', (r) => r.max_periods_per_week],
        ]}
      />
      <Table
        title="Weekly plan"
        rows={data.requirements}
        cols={[['Section', (r) => sec[r.class_group_id]], ['Subject', (r) => subj[r.subject_id]], ['Periods', (r) => r.periods_per_week], ['Teacher', (r) => tch[r.preferred_teacher_id]]]}
      />
      <Table title="Rules" rows={data.constraints} cols={[['Rule', (r) => r.description || r.source_text || r.type], ['Required', (r) => (r.is_hard ? 'Yes' : 'Preference')]]} />
      <Table title="Rooms" rows={data.rooms} cols={[['Name', (r) => r.name], ['Type', (r) => r.room_type], ['Capacity', (r) => r.capacity]]} />
      <Table title="Timetables" rows={data.timetables} cols={[['Name', (r) => r.name || `#${r.id}`], ['Status', (r) => r.status], ['Lessons', (r) => r.lessons], ['Made', (r) => (r.created_at || '').slice(0, 10)]]} />
    </div>
  )
}
