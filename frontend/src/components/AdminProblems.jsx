import { useEffect, useState } from 'react'
import { api } from '../api'

/**
 * Admin > Problems: where schools get stuck - failed generations, moves that
 * couldn't be made, setup problems, and "Send to support" requests with the
 * school's setup attached. The most common ones come first: a fix there
 * helps every school that hits it. See backend/app/services/problem_log.py.
 */

export const PROBLEM_KINDS = {
  generation_failed: 'Generation failed',
  move_blocked: 'Move blocked',
  setup_error: 'Setup problem',
  support_request: 'Sent to support',
}

const STATUSES = [
  ['open', 'Open'],
  ['fixed', 'Fixed in the product'],
  ['school_setup', "School's own setup"],
  ['wont_fix', "Won't fix"],
]

const CHECK_LABELS = {
  section_overfull: 'Section needs more periods than its week',
  teacher_overloaded: 'Teacher alone over their limit',
  staffing: "Sections can't be shared out",
  block_teacher_clash: 'Shared block needs one teacher twice',
  lab_batches: 'Split lab short of teachers',
  double_periods: "Back-to-back rule can't fit",
  no_periods: 'No periods set up',
}

export default function AdminProblems() {
  const [kind, setKind] = useState('')
  const [status, setStatus] = useState('open')
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  function load() {
    setError(null)
    api.admin
      .problems({ kind, status, q })
      .then(setData)
      .catch((e) => setError(e.message))
  }
  useEffect(load, [kind, status]) // eslint-disable-line react-hooks/exhaustive-deps

  async function mark(p, next) {
    setData((d) => ({ ...d, problems: d.problems.map((x) => (x.id === p.id ? { ...x, status: next } : x)) }))
    try {
      await api.admin.updateProblem(p.id, { status: next })
    } catch (e) {
      setError(e.message)
    }
  }

  async function download(p) {
    try {
      await api.admin.downloadProblemSnapshot(p)
    } catch (e) {
      setError(e.message)
    }
  }

  const counts = data?.counts ?? {}
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Problems</h2>
        <p className="mt-1 text-sm text-slate-500">
          Where schools got stuck in the last 30 days. Fix the common ones in the product; mark the rest as the
          school&rsquo;s own setup.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        {Object.entries(PROBLEM_KINDS).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setKind(kind === k ? '' : k)}
            aria-pressed={kind === k}
            className={`rounded-lg border bg-white p-4 text-left ${kind === k ? 'border-neutral-900' : 'border-slate-200 hover:border-slate-300'}`}
          >
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight">{counts[k] ?? 0}</p>
            <p className="mt-0.5 text-xs text-slate-500">open</p>
          </button>
        ))}
      </div>

      {data?.common?.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-medium">Most common</h3>
          <ol className="mt-2 flex flex-col gap-1 text-sm">
            {data.common.map((c, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span className="text-slate-700">
                  <span className="text-slate-400">{PROBLEM_KINDS[c.kind] ?? c.kind}:</span>{' '}
                  {c.kind === 'setup_error' ? CHECK_LABELS[c.label] ?? c.label : c.label}
                </span>
                <span className="flex-none text-slate-500">
                  {c.schools} {c.schools === 1 ? 'school' : 'schools'}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        >
          {STATUSES.map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
          <option value="all">Any status</option>
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
            placeholder="Search"
            aria-label="Search problems"
            className="w-56 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <button className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50">Search</button>
        </form>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex flex-col gap-3">
        {data == null && <p className="text-sm text-slate-400">Loading…</p>}
        {data?.problems.length === 0 && (
          <p className="rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">Nothing here.</p>
        )}
        {data?.problems.map((p) => (
          <article key={p.id} className="rounded-lg border border-slate-200 bg-white p-4" aria-label={`Problem ${p.id}`}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-slate-500">
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-700">{PROBLEM_KINDS[p.kind] ?? p.kind}</span>
              <span>{p.school_name ?? 'Unknown school'}</span>
              <span>{p.created_at ? new Date(p.created_at).toLocaleString('en-IN') : ''}</span>
              <span>#{p.id}</span>
            </div>
            <p className="mt-2 text-[15px] text-slate-900">{p.summary}</p>
            <ProblemDetail p={p} />
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {STATUSES.map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={p.status === id}
                  onClick={() => mark(p, id)}
                  className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                    p.status === id ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {label}
                </button>
              ))}
              {p.has_snapshot && (
                <button
                  type="button"
                  onClick={() => download(p)}
                  className="ml-auto rounded border border-slate-300 px-2.5 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Download setup
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function ProblemDetail({ p }) {
  const d = p.detail || {}
  const ctx = d.context || {}
  const reasons = d.reasons || ctx.reasons
  const lines = [
    ['Message', d.message],
    ['From', d.email],
    ['Where', ctx.where],
    ['Lesson', d.lesson ? `${d.lesson}, ${d.from} → ${d.to}` : null],
    ['Fixes offered', d.fixes_found != null ? String(d.fixes_found) : null],
    ['Check', d.check ? CHECK_LABELS[d.check] ?? d.check : null],
    ['Reason', ctx.reason],
  ].filter(([, v]) => v)
  return (
    <>
      {lines.length > 0 && (
        <dl className="mt-2 grid gap-x-3 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
          {lines.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-slate-500">{k}</dt>
              <dd className="text-slate-700">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {Array.isArray(reasons) && reasons.length > 1 && (
        <ol className="mt-2 list-decimal pl-5 text-sm text-slate-700">
          {reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ol>
      )}
    </>
  )
}
