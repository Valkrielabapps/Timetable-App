import { useEffect, useState } from 'react'
import { api } from '../api'
import { formatDate } from './BillingSection'
import { confirmDialog } from './confirmDialog'

const STATUS_STYLE = {
  free: 'bg-slate-100 text-slate-700',
  active: 'bg-emerald-50 text-emerald-700',
  grace: 'bg-amber-50 text-amber-800',
  locked: 'bg-red-50 text-red-700',
}

const limitText = (v) => (v == null ? 'unlimited' : v)

/**
 * Timetablz admin page (staff only - PLATFORM_ADMIN_EMAILS on the backend).
 *
 * Every school with its plan and status, and the actions a SaaS billing desk
 * needs: make a custom offer, record a bank transfer, give more free days,
 * downgrade after a refund. Recent invoices underneath.
 */
export default function AdminTab({ statusFilter = 'all' }) {
  const [schools, setSchools] = useState([])
  const [invoices, setInvoices] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [openId, setOpenId] = useState(null)

  async function load(q = query) {
    setError(null)
    try {
      const [s, i] = await Promise.all([api.admin.schools(q), api.admin.invoices()])
      setSchools(s)
      setInvoices(i)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Schools</h2>
          <p className="mt-1 text-sm text-slate-500">Every school, its plan and status. Manage to make a custom offer, record a payment, extend free days or downgrade.</p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            load(query)
          }}
          className="flex gap-2"
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search schools"
            aria-label="Search schools"
            className="w-56 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <button className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-50">Search</button>
        </form>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2.5 font-medium">School</th>
              <th className="px-4 py-2.5 font-medium">Plan</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium">Sections</th>
              <th className="px-4 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">Loading…</td>
              </tr>
            )}
            {!loading && schools.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">No schools found.</td>
              </tr>
            )}
            {schools.filter((s) => statusFilter === 'all' || s.status === statusFilter).map((s) => (
              <SchoolRow
                key={s.id}
                school={s}
                open={openId === s.id}
                onToggle={() => setOpenId(openId === s.id ? null : s.id)}
                onChanged={() => load()}
              />
            ))}
          </tbody>
        </table>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h3 className="text-base font-semibold">Recent invoices</h3>
        {invoices.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No invoices yet.</p>
        ) : (
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-2 font-medium">Number</th>
                <th className="py-2 font-medium">School</th>
                <th className="py-2 font-medium">Description</th>
                <th className="py-2 font-medium">Amount</th>
                <th className="py-2 font-medium">Paid</th>
                <th className="py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id} className="border-t border-slate-100">
                  <td className="py-2 font-medium">{inv.number}</td>
                  <td className="py-2">{inv.school_name}</td>
                  <td className="py-2 text-slate-600">{inv.description}</td>
                  <td className="py-2">₹{Number(inv.amount).toLocaleString('en-IN')}</td>
                  <td className="py-2 text-slate-600">
                    {formatDate(inv.issued_at)} · {inv.method === 'online' ? 'Online' : 'Bank transfer'}
                  </td>
                  <td className="py-2 text-right">
                    <button onClick={() => api.downloadInvoice(inv)} className="text-xs font-medium underline underline-offset-2">
                      PDF
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

function SchoolRow({ school, open, onToggle, onChanged }) {
  const s = school
  const statusText =
    s.status === 'free'
      ? `Free · ${s.free_days_left ?? '?'} days left`
      : s.status === 'active'
        ? s.plan_valid_until
          ? `Active until ${formatDate(s.plan_valid_until)}`
          : 'Active'
        : s.status === 'grace'
          ? `Grace (ended ${formatDate(s.plan_valid_until)})`
          : 'Locked'
  return (
    <>
      <tr className="border-t border-slate-100">
        <td className="px-4 py-3">
          <p className="font-medium">{s.name}</p>
          <p className="text-xs text-slate-500">{s.owner_email ?? 'no owner'}</p>
        </td>
        <td className="px-4 py-3">
          {s.plan_name}
          {s.open_offer && (
            <p className="text-xs text-amber-700">
              Offer open: ₹{s.open_offer.price_inr.toLocaleString('en-IN')}
            </p>
          )}
        </td>
        <td className="px-4 py-3">
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[s.status] ?? ''}`}>{statusText}</span>
        </td>
        <td className="px-4 py-3">
          {s.sections} / {limitText(s.limits.max_sections)}
        </td>
        <td className="px-4 py-3 text-right">
          <button onClick={onToggle} aria-expanded={open} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium hover:bg-slate-50">
            {open ? 'Close' : 'Manage'}
          </button>
        </td>
      </tr>
      {open && (
        <tr className="border-t border-slate-100 bg-slate-50/60">
          <td colSpan={5} className="px-4 py-4">
            <SchoolActions school={s} onChanged={onChanged} />
          </td>
        </tr>
      )}
    </>
  )
}

function SchoolActions({ school, onChanged }) {
  const [busy, setBusy] = useState(null)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [offer, setOffer] = useState({ name: `${school.name} plan`, price_inr: '', period_days: 365, max_sections: '', max_members: '', note: '' })
  const [paid, setPaid] = useState({ kind: school.open_offer ? 'offer' : 'pro', amount_inr: school.open_offer?.price_inr ?? 4999, reference: '' })
  const [days, setDays] = useState(7)

  async function run(label, fn, success) {
    setBusy(label)
    setErr(null)
    setMsg(null)
    try {
      await fn()
      setMsg(success)
      onChanged()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(null)
    }
  }

  const num = (v) => (v === '' || v == null ? null : Number(v))

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <form
        className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4"
        onSubmit={(e) => {
          e.preventDefault()
          run('offer', () => api.admin.createOffer(school.id, {
            name: offer.name.trim(),
            price_inr: Number(offer.price_inr),
            period_days: Number(offer.period_days) || 365,
            max_sections: num(offer.max_sections),
            max_members: num(offer.max_members),
            note: offer.note.trim() || null,
          }), 'Offer sent. The school sees it in Settings > Plan & billing.')
        }}
      >
        <h4 className="text-sm font-semibold">Custom offer</h4>
        {school.open_offer && (
          <p className="text-xs text-amber-700">
            Open: {school.open_offer.name}, ₹{school.open_offer.price_inr.toLocaleString('en-IN')}. A new offer replaces it.
          </p>
        )}
        <Field label="Plan name" value={offer.name} onChange={(v) => setOffer({ ...offer, name: v })} required />
        <div className="grid grid-cols-2 gap-2">
          <Field label="Price (₹)" type="number" value={offer.price_inr} onChange={(v) => setOffer({ ...offer, price_inr: v })} required />
          <Field label="Days" type="number" value={offer.period_days} onChange={(v) => setOffer({ ...offer, period_days: v })} />
          <Field label="Max sections" type="number" placeholder="unlimited" value={offer.max_sections} onChange={(v) => setOffer({ ...offer, max_sections: v })} />
          <Field label="Max people" type="number" placeholder="unlimited" value={offer.max_members} onChange={(v) => setOffer({ ...offer, max_members: v })} />
        </div>
        <Field label="Note to the school (optional)" value={offer.note} onChange={(v) => setOffer({ ...offer, note: v })} />
        <div className="flex gap-2">
          <button disabled={busy != null} className="rounded-md bg-neutral-900 px-3 py-2 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-60">
            {busy === 'offer' ? 'Sending…' : 'Send offer'}
          </button>
          {school.open_offer && (
            <button
              type="button"
              disabled={busy != null}
              onClick={() => run('cancel', () => api.admin.cancelOffer(school.open_offer.id), 'Offer withdrawn.')}
              className="rounded-md border border-slate-300 px-3 py-2 text-xs font-medium hover:bg-slate-50"
            >
              Withdraw open offer
            </button>
          )}
        </div>
      </form>

      <form
        className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4"
        onSubmit={(e) => {
          e.preventDefault()
          run('paid', () => api.admin.markPaid(school.id, {
            kind: paid.kind,
            amount_inr: Number(paid.amount_inr),
            reference: paid.reference.trim() || null,
          }), 'Payment recorded, plan applied and invoice issued.')
        }}
      >
        <h4 className="text-sm font-semibold">Record a bank transfer</h4>
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          For
          <select
            value={paid.kind}
            onChange={(e) => setPaid({ ...paid, kind: e.target.value, amount_inr: e.target.value === 'offer' ? school.open_offer?.price_inr ?? '' : 4999 })}
            className="rounded-md border border-slate-300 px-2 py-2 text-sm text-slate-900"
          >
            <option value="pro">Pro, 1 year</option>
            {school.open_offer && <option value="offer">The open offer ({school.open_offer.name})</option>}
          </select>
        </label>
        <Field label="Amount received (₹)" type="number" value={paid.amount_inr} onChange={(v) => setPaid({ ...paid, amount_inr: v })} required />
        <Field label="Reference (UTR / cheque no.)" value={paid.reference} onChange={(v) => setPaid({ ...paid, reference: v })} />
        <div>
          <button disabled={busy != null} className="rounded-md bg-neutral-900 px-3 py-2 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-60">
            {busy === 'paid' ? 'Saving…' : 'Mark as paid'}
          </button>
        </div>
      </form>

      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4">
        <h4 className="text-sm font-semibold">Free period &amp; plan</h4>
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            run('extend', () => api.admin.extendFree(school.id, Number(days)), `Added ${days} free days.`)
          }}
        >
          <Field label="Extra free days" type="number" value={days} onChange={setDays} />
          <button disabled={busy != null} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-medium hover:bg-slate-50">
            Extend
          </button>
        </form>
        <p className="text-xs text-slate-500">
          Plan: {school.plan_name}. Limits: {limitText(school.limits.max_sections)} sections, {limitText(school.limits.max_members)} people.
        </p>
        {school.paid_plan && (
          <button
            disabled={busy != null}
            onClick={async () => {
              const ok = await confirmDialog({
                title: `Downgrade ${school.name}?`,
                message: 'Ends their paid plan now (for example after a refund). They return to any free days left, otherwise the school is locked. Invoices are kept.',
                confirmLabel: 'Downgrade',
                danger: true,
              })
              if (ok) run('down', () => api.admin.downgrade(school.id), 'Plan ended.')
            }}
            className="w-fit rounded-md border border-red-200 px-3 py-2 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            Downgrade (after refund)
          </button>
        )}
      </div>

      {(msg || err) && (
        <p className={`text-sm lg:col-span-3 ${err ? 'text-red-600' : 'text-emerald-700'}`} role="status">
          {err || msg}
        </p>
      )}
    </div>
  )
}

function Field({ label, value, onChange, type = 'text', placeholder, required }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-500">
      {label}
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        required={required}
        min={type === 'number' ? 1 : undefined}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 px-2 py-2 text-sm text-slate-900 focus:border-neutral-900 focus:outline-none"
      />
    </label>
  )
}
