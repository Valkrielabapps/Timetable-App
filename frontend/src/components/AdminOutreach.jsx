import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { confirmDialog } from './confirmDialog'

/**
 * Admin page > Outreach: Timetablz's own sales pipeline.
 *
 * The school list (imported from the outreach workbook), who to write to at
 * each school, the emails drafted for them, and everything sent and
 * received. Emails are only ever sent once approved here, from the connected
 * Gmail mailbox, a few at a time inside school hours - see
 * backend/app/services/outreach.py.
 */

export const STATUS_LABELS = {
  not_contacted: 'Not contacted',
  emailed: 'Emailed',
  replied: 'Replied',
  bounced: 'Bounced',
  opted_out: 'Opted out',
  demo_booked: 'Demo booked',
  trial: 'Trial',
  paid: 'Paid',
  not_interested: 'Not interested',
}

const STATUS_TONE = {
  not_contacted: 'bg-slate-100 text-slate-600',
  emailed: 'bg-sky-50 text-sky-700',
  replied: 'bg-emerald-50 text-emerald-700',
  bounced: 'bg-red-50 text-red-700',
  opted_out: 'bg-amber-50 text-amber-800',
  demo_booked: 'bg-violet-50 text-violet-700',
  trial: 'bg-violet-50 text-violet-700',
  paid: 'bg-emerald-100 text-emerald-800',
  not_interested: 'bg-slate-100 text-slate-500',
}

const VIEWS = [
  ['schools', 'Schools'],
  ['review', 'Review emails'],
  ['activity', 'Activity'],
  ['settings', 'Settings'],
]

export default function AdminOutreach({ notice = null }) {
  const [overview, setOverview] = useState(null)
  const [view, setView] = useState('schools')
  const [error, setError] = useState(null)
  const [flash, setFlash] = useState(notice)

  const refresh = useCallback(() => {
    api.admin.outreach.overview().then(setOverview).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // While contacts are being looked up, keep the numbers moving.
  useEffect(() => {
    if (!overview?.job?.running) return
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [overview?.job?.running, refresh])

  return (
    <div className="flex flex-col gap-6">
      {flash && (
        <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {flash}{' '}
          <button onClick={() => setFlash(null)} className="ml-2 text-xs underline">Dismiss</button>
        </p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <SendingBar overview={overview} onChange={refresh} onError={setError} />
      <Numbers overview={overview} />
      <nav className="flex gap-1 border-b border-slate-200 text-sm" aria-label="Outreach sections">
        {VIEWS.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setView(id)}
            aria-current={view === id ? 'page' : undefined}
            className={`-mb-px border-b-2 px-3 py-2 font-medium ${
              view === id ? 'border-neutral-900 text-neutral-900' : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            {label}
            {id === 'review' && overview?.awaiting_approval > 0 && (
              <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 text-xs text-amber-800">{overview.awaiting_approval}</span>
            )}
          </button>
        ))}
      </nav>
      {view === 'schools' && <Schools job={overview?.job} onChange={refresh} onFlash={setFlash} />}
      {view === 'review' && <Review onChange={refresh} />}
      {view === 'activity' && <Activity />}
      {view === 'settings' && <Settings onChange={refresh} />}
    </div>
  )
}

function SendingBar({ overview, onChange, onError }) {
  const [busy, setBusy] = useState(false)
  if (!overview) return null

  async function connect() {
    onError(null)
    try {
      const { url } = await api.admin.outreach.connectGmail()
      window.location.assign(url)
    } catch (e) {
      onError(e.message)
    }
  }

  async function toggle() {
    setBusy(true)
    onError(null)
    try {
      await api.admin.outreach.saveSettings({ sending_enabled: !overview.sending_enabled })
      onChange()
    } catch (e) {
      onError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <div>
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Mailbox</div>
        {overview.mailbox_connected ? (
          <div className="font-medium">{overview.mailbox}</div>
        ) : overview.gmail_configured ? (
          <button onClick={connect} className="mt-0.5 rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white hover:bg-neutral-700">
            Connect Gmail
          </button>
        ) : (
          <div className="text-amber-700">Not set up on the server yet (see Settings)</div>
        )}
      </div>
      <div>
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Sending</div>
        <label className="mt-0.5 flex items-center gap-2">
          <input
            type="checkbox"
            role="switch"
            aria-label="Sending on"
            checked={overview.sending_enabled}
            disabled={busy || !overview.mailbox_connected}
            onChange={toggle}
            className="h-4 w-4"
          />
          <span className={overview.sending_enabled ? 'font-medium text-emerald-700' : 'text-slate-600'}>
            {overview.sending_enabled ? 'On' : 'Off'}
          </span>
        </label>
      </div>
      <div>
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Today</div>
        <div>
          <span className="font-medium">{overview.sent_today}</span> of {overview.daily_limit} sent
          {overview.daily_limit < overview.daily_limit_set && (
            <span className="ml-1 text-xs text-slate-500">(warming up the mailbox)</span>
          )}
        </div>
      </div>
      <div className="text-xs text-slate-500">
        {overview.in_send_window
          ? 'Inside sending hours (Mon to Sat, 9:30 to 4:30 India time).'
          : 'Outside sending hours: emails wait until Mon to Sat, 9:30 to 4:30 India time.'}
      </div>
    </div>
  )
}

function Numbers({ overview }) {
  if (!overview) return null
  const s = overview.by_status
  const cards = [
    ['Schools', overview.schools, `${overview.with_email} with an email`],
    ['Principal found', overview.with_principal, 'Named on their website'],
    ['To review', overview.awaiting_approval, 'Drafted, not approved'],
    ['Queued', overview.queued, 'Approved, first email not sent'],
    ['Sent this week', overview.sent_this_week, 'Emails, follow-ups included'],
    ['Replied', s.replied, `${s.opted_out} opted out · ${s.bounced} bounced`],
    ['Demo booked', s.demo_booked, `${s.trial} on trial · ${s.paid} paid`],
  ]
  return (
    <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-7">
      {cards.map(([label, value, hint]) => (
        <div key={label} className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="text-xs text-slate-500">{label}</div>
          <div className="mt-0.5 text-xl font-semibold">{value ?? '—'}</div>
          <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------

function sequenceText(seq) {
  if (!seq) return '—'
  if (seq.status === 'draft') return 'Drafted'
  if (seq.status === 'approved') return 'Approved'
  if (seq.status === 'sent') return `Email ${seq.step} sent`
  if (seq.status === 'failed') return 'Failed'
  return 'Stopped'
}

function Schools({ job, onChange, onFlash }) {
  const [filters, setFilters] = useState({ q: '', status: '', priority: '', district: '', has_email: '' })
  const [data, setData] = useState({ schools: [], districts: [] })
  const [selected, setSelected] = useState([])
  const [open, setOpen] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const fileRef = useRef(null)

  const load = useCallback(() => {
    api.admin.outreach.schools(filters).then(setData).catch((e) => setError(e.message))
  }, [filters])

  useEffect(() => {
    const t = setTimeout(load, 200)
    return () => clearTimeout(t)
  }, [load])

  // Reload the list when a contact search finishes.
  const wasRunning = useRef(false)
  useEffect(() => {
    if (wasRunning.current && !job?.running) load()
    wasRunning.current = !!job?.running
  }, [job?.running, load])

  const shownIds = data.schools.map((s) => s.id)
  const allShown = shownIds.length > 0 && shownIds.every((id) => selected.includes(id))
  const toggle = (id) => setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  async function act(kind) {
    if (!selected.length) return
    setBusy(kind)
    setError(null)
    try {
      if (kind === 'find') {
        await api.admin.outreach.findContacts(selected)
        onFlash(`Looking for contacts on ${selected.length} school website${selected.length === 1 ? '' : 's'}…`)
      } else if (kind === 'draft') {
        const r = await api.admin.outreach.draft(selected)
        onFlash(
          `Drafted emails for ${r.created} school${r.created === 1 ? '' : 's'}` +
            (r.skipped ? ` (${r.skipped} skipped: no email, already in a sequence, or closed)` : '') +
            '. Review them in Review emails.',
        )
      } else if (kind === 'approve') {
        const r = await api.admin.outreach.approve(selected)
        onFlash(`Approved ${r.approved} email${r.approved === 1 ? '' : 's'}.`)
      } else if (kind === 'stop') {
        const ok = await confirmDialog({
          title: 'Stop emails to these schools?',
          message: 'Anything not yet sent to them is cancelled.',
          confirmLabel: 'Stop',
          danger: true,
        })
        if (!ok) return
        await api.admin.outreach.cancel(selected)
      }
      setSelected([])
      load()
      onChange()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  async function importFile(file) {
    if (!file) return
    setBusy('import')
    setError(null)
    try {
      const r = await api.admin.outreach.importWorkbook(file)
      onFlash(`Imported: ${r.added} new school${r.added === 1 ? '' : 's'}, ${r.updated} updated. ${r.total} on the list.`)
      load()
      onChange()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function save(id, change) {
    try {
      const updated = await api.admin.outreach.editSchool(id, change)
      setData((d) => ({ ...d, schools: d.schools.map((s) => (s.id === id ? { ...s, ...updated } : s)) }))
      onChange()
    } catch (e) {
      setError(e.message)
    }
  }

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))
  const selectCls = 'rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm'

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input value={filters.q} onChange={set('q')} placeholder="Search school, area, group" aria-label="Search schools"
               className="w-64 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm" />
        <select value={filters.status} onChange={set('status')} aria-label="Status" className={selectCls}>
          <option value="">Any status</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={filters.priority} onChange={set('priority')} aria-label="Priority" className={selectCls}>
          <option value="">Any priority</option>
          <option value="High">High</option>
          <option value="Medium">Medium</option>
          <option value="Low">Low</option>
        </select>
        <select value={filters.district} onChange={set('district')} aria-label="District" className={selectCls}>
          <option value="">Any district</option>
          {data.districts.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select value={filters.has_email} onChange={set('has_email')} aria-label="Email" className={selectCls}>
          <option value="">With or without email</option>
          <option value="true">Has an email</option>
          <option value="false">No email</option>
        </select>
        <div className="ml-auto flex items-center gap-2">
          <input ref={fileRef} type="file" accept=".xlsx" className="hidden" aria-label="Workbook file"
                 onChange={(e) => importFile(e.target.files?.[0])} />
          <button onClick={() => fileRef.current?.click()} disabled={busy === 'import'}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-50">
            {busy === 'import' ? 'Importing…' : 'Import workbook'}
          </button>
        </div>
      </div>

      {job?.kind === 'find_contacts' && (job.running || job.finished_at) && (
        <p className="text-sm text-slate-600">
          {job.running ? 'Looking for contacts: ' : 'Contact search finished: '}
          {job.done} of {job.total} websites checked, principal found for {job.found}.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 rounded-md bg-slate-100 px-3 py-2 text-sm">
        <span className="text-slate-600">{selected.length} selected</span>
        {[
          ['find', 'Find contacts', 'Read their websites for the principal’s name'],
          ['draft', 'Draft emails', 'Write the 3-email sequence; nothing is sent'],
          ['approve', 'Approve', 'Approve their drafted emails for sending'],
          ['stop', 'Stop emails', 'Cancel anything not yet sent'],
        ].map(([kind, label, title]) => (
          <button key={kind} onClick={() => act(kind)} disabled={!selected.length || !!busy || (kind === 'find' && job?.running)}
                  title={title}
                  className={`rounded-md px-3 py-1 font-medium disabled:opacity-40 ${
                    kind === 'stop' ? 'text-red-700 hover:bg-red-50' : 'bg-white text-slate-800 shadow-sm hover:bg-slate-50'
                  }`}>
            {busy === kind ? '…' : label}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="p-2">
                <input type="checkbox" aria-label="Select all shown" checked={allShown}
                       onChange={() => setSelected(allShown ? selected.filter((id) => !shownIds.includes(id)) : [...new Set([...selected, ...shownIds])])} />
              </th>
              <th className="p-2">School</th>
              <th className="p-2">Priority</th>
              <th className="p-2">Who to write to</th>
              <th className="p-2">Email</th>
              <th className="p-2">Emails</th>
              <th className="p-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.schools.length === 0 && (
              <tr><td colSpan={7} className="p-6 text-center text-slate-500">No schools here yet. Import the outreach workbook to start.</td></tr>
            )}
            {data.schools.map((s) => (
              <SchoolRow key={s.id} school={s} checked={selected.includes(s.id)} onCheck={() => toggle(s.id)}
                         open={open === s.id} onOpen={() => setOpen(open === s.id ? null : s.id)} onSave={save} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">{data.schools.length} school{data.schools.length === 1 ? '' : 's'} shown.</p>
    </div>
  )
}

function SchoolRow({ school: s, checked, onCheck, open, onOpen, onSave }) {
  const contact = s.principal_name
    ? `${s.principal_name} (Principal)`
    : s.contact_name
    ? `${s.contact_name}${s.contact_role ? ` (${s.contact_role})` : ''}`
    : null
  return (
    <>
      <tr className="border-b border-slate-100 align-top hover:bg-slate-50/60">
        <td className="p-2"><input type="checkbox" aria-label={`Select ${s.name}`} checked={checked} onChange={onCheck} /></td>
        <td className="p-2">
          <button onClick={onOpen} className="text-left font-medium hover:underline">{s.name}</button>
          <div className="text-xs text-slate-500">
            {[s.area, s.district, s.classes_up_to, s.group_name].filter(Boolean).join(' · ')}
          </div>
        </td>
        <td className="p-2 text-xs">{s.priority ?? '—'}</td>
        <td className="p-2 text-xs">{contact ?? <span className="text-slate-400">Principal</span>}</td>
        <td className="p-2 text-xs">{s.recipient ?? <span className="text-slate-400">None found</span>}</td>
        <td className="p-2 text-xs">{sequenceText(s.sequence)}</td>
        <td className="p-2">
          <select value={s.status} aria-label={`Status of ${s.name}`} onChange={(e) => onSave(s.id, { status: e.target.value })}
                  className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_TONE[s.status] ?? ''}`}>
            {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </td>
      </tr>
      {open && (
        <tr className="border-b border-slate-200 bg-slate-50/70">
          <td />
          <td colSpan={6} className="p-3">
            <SchoolDetail school={s} onSave={onSave} />
          </td>
        </tr>
      )}
    </>
  )
}

function SchoolDetail({ school: s, onSave }) {
  const [form, setForm] = useState({
    principal_name: s.principal_name ?? '',
    contact_name: s.contact_name ?? '',
    contact_role: s.contact_role ?? '',
    to_email: s.to_email ?? '',
    phone: s.phone ?? '',
    next_step: s.next_step ?? '',
    next_date: s.next_date ?? '',
    notes: s.notes ?? '',
  })
  const [saved, setSaved] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const input = 'w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm'

  async function submit(e) {
    e.preventDefault()
    const change = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null]))
    await onSave(s.id, change)
    setSaved(true)
  }

  return (
    <form onSubmit={submit} aria-label={`Details for ${s.name}`} className="grid gap-3 text-sm md:grid-cols-3">
      <label className="flex flex-col gap-1 text-xs text-slate-500">Principal
        <input value={form.principal_name} onChange={set('principal_name')} className={input} />
        {s.contact_source && <a href={s.contact_source} target="_blank" rel="noreferrer" className="truncate text-[11px] text-sky-700 underline">Found on {s.contact_source}</a>}
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">Other contact
        <input value={form.contact_name} onChange={set('contact_name')} className={input} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">Their role
        <input value={form.contact_role} onChange={set('contact_role')} placeholder="Vice Principal, Coordinator…" className={input} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">Send emails to
        <select value={form.to_email} onChange={set('to_email')} className={input}>
          <option value="">{s.emails[0] ? `${s.emails[0]} (first found)` : 'No email yet'}</option>
          {s.emails.slice(1).map((e) => <option key={e} value={e}>{e}</option>)}
          {form.to_email && !s.emails.includes(form.to_email) && <option value={form.to_email}>{form.to_email}</option>}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">Phone
        <input value={form.phone} onChange={set('phone')} className={input} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">Website
        {s.website ? <a href={s.website} target="_blank" rel="noreferrer" className="truncate py-1 text-sky-700 underline">{s.website}</a> : <span className="py-1">—</span>}
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">Next step
        <input value={form.next_step} onChange={set('next_step')} placeholder="Call the office, visit…" className={input} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">Next date
        <input type="date" value={form.next_date} onChange={set('next_date')} className={input} />
      </label>
      <div />
      <label className="flex flex-col gap-1 text-xs text-slate-500 md:col-span-3">Notes (replies are added here)
        <textarea value={form.notes} onChange={set('notes')} rows={3} className={input} />
      </label>
      <div className="flex items-center gap-3 md:col-span-3">
        <button type="submit" className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700">Save</button>
        {saved && <span className="text-xs text-emerald-700">Saved</span>}
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------

function Review({ onChange }) {
  const [messages, setMessages] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.admin.outreach.messages({ status: 'draft' }).then(setMessages).catch((e) => setError(e.message))
  }, [])
  useEffect(load, [load])

  const bySchool = useMemo(() => {
    const out = new Map()
    for (const m of messages ?? []) {
      if (!out.has(m.school_id)) out.set(m.school_id, { name: m.school_name, to: m.to_email, steps: [] })
      out.get(m.school_id).steps.push(m)
    }
    for (const v of out.values()) v.steps.sort((a, b) => a.step - b.step)
    return [...out.entries()]
  }, [messages])

  async function decide(ids, approve) {
    setBusy(true)
    setError(null)
    try {
      if (approve) await api.admin.outreach.approve(ids)
      else await api.admin.outreach.cancel(ids)
      load()
      onChange()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (messages === null) return <p className="text-sm text-slate-500">Loading…</p>
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-slate-600">
          {bySchool.length
            ? `${bySchool.length} school${bySchool.length === 1 ? '' : 's'} with emails to review. Approving a school approves its first email and both follow-ups.`
            : 'Nothing to review. Select schools on the Schools tab and choose Draft emails.'}
        </p>
        {bySchool.length > 1 && (
          <button onClick={() => decide(bySchool.map(([id]) => id), true)} disabled={busy}
                  className="ml-auto rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50">
            Approve all {bySchool.length}
          </button>
        )}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {bySchool.map(([schoolId, s]) => (
        <ReviewCard key={schoolId} school={s} busy={busy}
                    onApprove={() => decide([schoolId], true)} onDiscard={() => decide([schoolId], false)} />
      ))}
    </div>
  )
}

function ReviewCard({ school, busy, onApprove, onDiscard }) {
  const [step, setStep] = useState(1)
  const message = school.steps.find((m) => m.step === step) ?? school.steps[0]
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4" aria-label={`Emails to ${school.name}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium">{school.name}</h3>
        <span className="text-xs text-slate-500">to {school.to}</span>
        <div className="ml-auto flex gap-1 text-xs" role="group" aria-label="Which email">
          {school.steps.map((m) => (
            <button key={m.id} onClick={() => setStep(m.step)} aria-pressed={step === m.step}
                    className={`rounded-full border px-2.5 py-0.5 ${step === m.step ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 text-slate-600'}`}>
              {m.step === 1 ? 'First email' : `Follow-up ${m.step - 1}`}
            </button>
          ))}
        </div>
      </div>
      {message && <MessageEditor key={message.id} message={message} />}
      <div className="mt-3 flex gap-2">
        <button onClick={onApprove} disabled={busy}
                className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50">
          Approve
        </button>
        <button onClick={onDiscard} disabled={busy} className="rounded-md px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50">
          Discard
        </button>
      </div>
    </article>
  )
}

function MessageEditor({ message }) {
  const [subject, setSubject] = useState(message.subject)
  const [body, setBody] = useState(message.body)
  const [state, setState] = useState(null)
  const dirty = subject !== message.subject || body !== message.body

  async function save() {
    setState('saving')
    try {
      await api.admin.outreach.editMessage(message.id, { subject, body })
      message.subject = subject
      message.body = body
      setState('saved')
    } catch (e) {
      setState(e.message)
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2">
      <input value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject"
             className="rounded border border-slate-300 px-2 py-1 text-sm font-medium" />
      <textarea value={body} onChange={(e) => setBody(e.target.value)} aria-label="Email" rows={12}
                className="rounded border border-slate-300 px-2 py-1.5 font-sans text-sm leading-relaxed" />
      {(dirty || state) && (
        <div className="flex items-center gap-2 text-xs">
          {dirty && <button onClick={save} className="rounded border border-slate-300 px-2 py-1 font-medium hover:bg-slate-50">Save changes</button>}
          {state === 'saved' && !dirty && <span className="text-emerald-700">Saved</span>}
          {state && !['saving', 'saved'].includes(state) && <span className="text-red-600">{state}</span>}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

const ACTIVITY_FILTERS = [
  ['sent', 'Sent'],
  ['approved', 'Waiting to send'],
  ['failed', 'Failed'],
  ['cancelled', 'Stopped'],
]

function Activity() {
  const [filter, setFilter] = useState('sent')
  const [messages, setMessages] = useState(null)
  const [replies, setReplies] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    setMessages(null)
    api.admin.outreach.messages({ status: filter }).then(setMessages).catch((e) => setError(e.message))
  }, [filter])
  useEffect(() => {
    api.admin.outreach.schools({ status: 'replied' }).then((d) => setReplies(d.schools)).catch(() => {})
  }, [])

  const when = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—')

  return (
    <div className="flex flex-col gap-5">
      {replies.length > 0 && (
        <section aria-label="Replies">
          <h3 className="mb-2 text-sm font-medium">Replies to follow up ({replies.length})</h3>
          <ul className="flex flex-col gap-2">
            {replies.map((s) => (
              <li key={s.id} className="rounded-md border border-emerald-200 bg-emerald-50/50 p-3 text-sm">
                <span className="font-medium">{s.name}</span>
                <span className="ml-2 text-xs text-slate-500">{s.recipient}</span>
                {s.notes && <p className="mt-1 whitespace-pre-line text-xs text-slate-700">{s.notes.split('\n').slice(-1)[0]}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="flex gap-2" role="group" aria-label="Which emails">
        {ACTIVITY_FILTERS.map(([id, label]) => (
          <button key={id} onClick={() => setFilter(id)} aria-pressed={filter === id}
                  className={`rounded-full border px-3 py-1 text-sm ${filter === id ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 bg-white text-slate-700'}`}>
            {label}
          </button>
        ))}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {messages === null ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : messages.length === 0 ? (
        <p className="text-sm text-slate-500">Nothing here.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="p-2">{filter === 'sent' ? 'Sent' : filter === 'approved' ? 'Not before' : 'Approved'}</th>
                <th className="p-2">School</th>
                <th className="p-2">Email</th>
                <th className="p-2">To</th>
                <th className="p-2">Subject</th>
                {(filter === 'failed' || filter === 'cancelled') && <th className="p-2">Why</th>}
              </tr>
            </thead>
            <tbody>
              {messages.map((m) => (
                <tr key={m.id} className="border-b border-slate-100">
                  <td className="p-2 text-xs text-slate-600">
                    {filter === 'sent' ? when(m.sent_at) : filter === 'approved' ? (m.step === 1 ? 'Next in line' : when(m.not_before)) : when(m.approved_at)}
                  </td>
                  <td className="p-2">{m.school_name}</td>
                  <td className="p-2 text-xs">{m.step === 1 ? 'First' : `Follow-up ${m.step - 1}`}</td>
                  <td className="p-2 text-xs">{m.to_email}</td>
                  <td className="p-2 text-xs">{m.subject}</td>
                  {(filter === 'failed' || filter === 'cancelled') && <td className="p-2 text-xs text-red-700">{m.error}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

function Settings({ onChange }) {
  const [form, setForm] = useState(null)
  const [state, setState] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.admin.outreach.settings().then(setForm).catch((e) => setError(e.message))
  }, [])

  if (!form) return error ? <p className="text-sm text-red-600">{error}</p> : <p className="text-sm text-slate-500">Loading…</p>

  const setTemplate = (step, field) => (e) =>
    setForm((f) => ({ ...f, templates: { ...f.templates, [step]: { ...f.templates[step], [field]: e.target.value } } }))

  async function save(e) {
    e.preventDefault()
    setState('saving')
    setError(null)
    try {
      const saved = await api.admin.outreach.saveSettings({
        sender_name: form.sender_name,
        signature: form.signature,
        templates: form.templates,
        daily_limit: Number(form.daily_limit),
        follow_up_days: form.follow_up_days.map(Number),
      })
      setForm(saved)
      setState('saved')
      onChange()
    } catch (err) {
      setError(err.message)
      setState(null)
    }
  }

  async function run(fn, done) {
    setError(null)
    try {
      const r = await fn()
      setState(done(r))
      onChange()
    } catch (err) {
      setError(err.message)
    }
  }

  async function disconnect() {
    const ok = await confirmDialog({
      title: 'Disconnect the mailbox?',
      message: 'Sending stops until a mailbox is connected again.',
      confirmLabel: 'Disconnect',
      danger: true,
    })
    if (ok) run(() => api.admin.outreach.disconnectGmail().then((r) => setForm(r)), () => 'Mailbox disconnected.')
  }

  const input = 'w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm'
  return (
    <form onSubmit={save} className="flex max-w-3xl flex-col gap-5" aria-label="Outreach settings">
      <section className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <h3 className="font-medium">Mailbox</h3>
        {form.mailbox_connected ? (
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <span>Sending from <span className="font-medium">{form.mailbox}</span></span>
            <button type="button" onClick={() => run(() => api.admin.outreach.sendTest(), (r) => `Test email sent to ${r.sent_to}.`)}
                    className="rounded border border-slate-300 px-2 py-1 text-xs font-medium hover:bg-slate-50">Send me a test email</button>
            <button type="button" onClick={() => run(() => api.admin.outreach.checkReplies(), (r) => `Checked: ${r.replied} replied, ${r.opted_out} opted out, ${r.bounced} bounced.`)}
                    className="rounded border border-slate-300 px-2 py-1 text-xs font-medium hover:bg-slate-50">Check replies now</button>
            <button type="button" onClick={disconnect} className="text-xs font-medium text-red-700 hover:underline">Disconnect</button>
          </div>
        ) : form.gmail_configured ? (
          <p className="mt-1 text-slate-600">Not connected. Use Connect Gmail at the top of this page.</p>
        ) : (
          <div className="mt-1 text-slate-600">
            <p>Gmail isn&rsquo;t set up on the server yet. In Google Cloud, create an OAuth client (Web application) with this redirect URI:</p>
            <code className="mt-1 block rounded bg-slate-100 px-2 py-1 text-xs">https://timetablz.com/api/admin/outreach/gmail/callback</code>
            <p className="mt-1">then add OUTREACH_GOOGLE_CLIENT_ID and OUTREACH_GOOGLE_CLIENT_SECRET in Railway.</p>
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Emails go one at a time, a few minutes apart, Monday to Saturday 9:30 to 4:30 India time. A new mailbox sends at
          most 10 a day for its first week and 20 in its second, and never more than {form.hard_daily_cap} a day.
        </p>
      </section>

      <section className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-slate-500">Sender name
          <input value={form.sender_name ?? ''} onChange={(e) => setForm({ ...form, sender_name: e.target.value })} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-500">Emails a day (most {form.hard_daily_cap})
          <input type="number" min="0" max={form.hard_daily_cap} value={form.daily_limit}
                 onChange={(e) => setForm({ ...form, daily_limit: e.target.value })} className={input} />
          <span className="text-[11px]">Today&rsquo;s limit while warming up: {form.effective_daily_limit}</span>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-500">Follow-up 1 after (days)
          <input type="number" min="1" max="30" value={form.follow_up_days[0]}
                 onChange={(e) => setForm({ ...form, follow_up_days: [e.target.value, form.follow_up_days[1]] })} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-500">Follow-up 2 after a further (days)
          <input type="number" min="1" max="30" value={form.follow_up_days[1]}
                 onChange={(e) => setForm({ ...form, follow_up_days: [form.follow_up_days[0], e.target.value] })} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-500 sm:col-span-2">Signature
          <textarea rows={3} value={form.signature ?? ''} onChange={(e) => setForm({ ...form, signature: e.target.value })} className={input} />
        </label>
      </section>

      <section className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white p-4">
        <div>
          <h3 className="text-sm font-medium">Templates</h3>
          <p className="mt-1 text-xs text-slate-500">
            Filled in for each school: {'{greeting}'} (Dr. Iyer, or Principal), {'{school}'}, {'{personal_line}'} (a sentence about
            that school), {'{sender_name}'}, {'{sender_first}'}, {'{signature}'}, {'{area}'}. Changes apply to emails drafted from now on.
          </p>
        </div>
        {['1', '2', '3'].map((step) => (
          <div key={step} className="flex flex-col gap-1.5">
            <div className="text-xs font-medium text-slate-600">{step === '1' ? 'First email' : `Follow-up ${Number(step) - 1}`}</div>
            <input aria-label={`Subject ${step}`} value={form.templates[step].subject} onChange={setTemplate(step, 'subject')} className={input} />
            <textarea aria-label={`Body ${step}`} rows={step === '1' ? 10 : 6} value={form.templates[step].body} onChange={setTemplate(step, 'body')} className={input} />
          </div>
        ))}
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex items-center gap-3">
        <button type="submit" className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700">Save settings</button>
        {state && state !== 'saving' && <span className="text-sm text-emerald-700">{state === 'saved' ? 'Saved' : state}</span>}
      </div>
    </form>
  )
}
