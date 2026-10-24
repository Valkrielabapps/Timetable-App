import { useEffect, useState } from 'react'
import { api } from '../api'

/**
 * Admin > Rule reading: sentences the rule parser struggled with in real use,
 * so each can be filed into what needs fixing. See
 * backend/app/services/rule_events.py for what is recorded and when.
 */

export const KIND_LABELS = {
  unclear: 'Asked a question',
  invalid: 'Read but refused',
  cancelled: 'Cancelled',
  reworded: 'Reworded',
  batch_unread: 'Handed back (batch)',
  not_applied: 'Saved, not applied',
  quick_delete: 'Deleted soon after',
  interpreted: 'Read',
  confirmed: 'Confirmed',
}

export const TRIAGE = [
  ['misread', 'Misread', 'Fix with an example or a prompt line'],
  ['checker', 'Checker', 'Read right, refused by the rule checker'],
  ['unsupported', 'Unsupported', 'Needs a new kind of rule'],
  ['ambiguous', 'Ambiguous', 'Needs a better question'],
  ['fine', 'Nothing wrong', ''],
]

const KIND_FILTERS = [['', 'Problems'], ...Object.entries(KIND_LABELS).filter(([k]) => k !== 'interpreted' && k !== 'confirmed'), ['all', 'Everything']]

export default function AdminRuleEvents() {
  const [kind, setKind] = useState('')
  const [triage, setTriage] = useState('none')
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  function load() {
    setError(null)
    api.admin
      .ruleEvents({ kind, triage, q })
      .then(setData)
      .catch((e) => setError(e.message))
  }
  useEffect(load, [kind, triage]) // eslint-disable-line react-hooks/exhaustive-deps

  async function file(event, value) {
    const next = event.triage === value ? null : value
    setData((d) => ({ ...d, events: d.events.map((e) => (e.id === event.id ? { ...e, triage: next } : e)) }))
    try {
      await api.admin.triageRuleEvent(event.id, next)
    } catch (e) {
      setError(e.message)
    }
  }

  const counts = data?.counts ?? {}
  const problems = Object.entries(counts)
    .filter(([k]) => k !== 'interpreted' && k !== 'confirmed')
    .reduce((n, [, v]) => n + v, 0)

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Rule reading</h2>
        <p className="mt-1 text-sm text-slate-500">
          Sentences schools typed that the rule parser struggled with, last 30 days. File each one so it can be fixed
          in the right place, then add the fixed phrasing to the catalogue.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Box label="Read into a rule" value={counts.interpreted ?? 0} />
        <Box
          label="Kept by the school"
          value={data?.confirmed_share == null ? '-' : `${Math.round(data.confirmed_share * 100)}%`}
          hint="Of the sentences read, how many were confirmed"
        />
        <Box label="Problems" value={problems} hint="Questions, refusals, cancels, rewords, quick deletes" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="What happened"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        >
          {KIND_FILTERS.map(([id, label]) => (
            <option key={id || 'problems'} value={id}>
              {label}
              {id && id !== 'all' && counts[id] ? ` (${counts[id]})` : ''}
            </option>
          ))}
        </select>
        <select
          aria-label="Filed as"
          value={triage}
          onChange={(e) => setTriage(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        >
          <option value="none">Not filed yet</option>
          <option value="">Filed or not</option>
          {TRIAGE.map(([id, label]) => (
            <option key={id} value={id}>
              Filed: {label}
            </option>
          ))}
        </select>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            load()
          }}
          className="flex gap-2"
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search the text"
            aria-label="Search rule text"
            className="w-56 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <button className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50">Search</button>
        </form>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex flex-col gap-3">
        {data == null && <p className="text-sm text-slate-400">Loading…</p>}
        {data?.events.length === 0 && <p className="rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">Nothing here.</p>}
        {data?.events.map((e) => (
          <article key={e.id} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-slate-500">
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-700">{KIND_LABELS[e.kind] ?? e.kind}</span>
              <span>{e.school_name ?? 'Unknown school'}</span>
              <span>{e.created_at ? new Date(e.created_at).toLocaleString('en-IN') : ''}</span>
            </div>
            <p className="mt-2 text-[15px] text-slate-900">&ldquo;{e.text}&rdquo;</p>
            <Detail detail={e.detail} />
            <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="File as">
              {TRIAGE.map(([id, label, hint]) => (
                <button
                  key={id}
                  type="button"
                  title={hint}
                  aria-pressed={e.triage === id}
                  onClick={() => file(e, id)}
                  className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                    e.triage === id ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function Detail({ detail }) {
  const lines = [
    ['Understood as', detail.sentence || detail.description || detail.was],
    ['Shown', detail.shown],
    ['Asked', detail.question],
    ['Why', detail.explanation || detail.reason || detail.error],
    ['Reworded to', detail.reworded_to],
    ['Deleted after', detail.minutes_after_saving != null ? `${detail.minutes_after_saving} min` : null],
  ].filter(([, v]) => v)
  if (lines.length === 0) return null
  return (
    <dl className="mt-2 grid gap-x-3 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
      {lines.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-slate-500">{k}</dt>
          <dd className="text-slate-700">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function Box({ label, value, hint }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}
