import { useEffect, useState } from 'react'
import { api, getToken, setToken } from '../api'
import AuthPage from './AuthPage'
import AdminTab from './AdminTab'
import AdminRuleEvents from './AdminRuleEvents'
import AdminOutreach from './AdminOutreach'

/**
 * timetablz.com/admin - the Valkyrie Labs console. A page of its own, outside
 * the school app: its own sign-in, no school sidebar.
 *
 * Only the account the backend recognises as a platform admin
 * (PLATFORM_ADMIN_EMAILS, valkyrielabapps@gmail.com by default) gets past the
 * gate. The check that matters is on the server - every /api/admin call is
 * refused for anyone else - this page just doesn't show them anything.
 */
export default function AdminPage() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  // Back from connecting Gmail: Google returns to /admin?outreach=...
  const outreachReturn = new URLSearchParams(window.location.search).get('outreach')
  const [view, setView] = useState(outreachReturn ? 'outreach' : 'dashboard')
  const outreachNotice = {
    gmail_connected: 'Gmail connected. Sending stays off until you switch it on.',
    gmail_cancelled: 'Connecting Gmail was cancelled.',
    gmail_failed: 'Gmail could not be connected. Try again.',
  }[outreachReturn] ?? null

  useEffect(() => {
    async function check() {
      if (!getToken()) {
        setChecking(false)
        return
      }
      try {
        setUser(await api.me())
      } catch {
        setToken(null)
      } finally {
        setChecking(false)
      }
    }
    check()
  }, [])

  function signOut() {
    setToken(null)
    setUser(null)
  }

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
      </div>
    )
  }

  if (!user) {
    return <AuthPage initialMode="login" onAuthenticated={setUser} onBack={() => window.location.assign('/')} />
  }

  if (!user.is_platform_admin) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="max-w-sm rounded-2xl border border-slate-200 bg-white p-8 text-center">
          <h1 className="text-lg font-semibold">This page isn&rsquo;t available</h1>
          <p className="mt-2 text-sm text-slate-600">You&rsquo;re signed in as {user.email}.</p>
          <div className="mt-6 flex justify-center gap-2">
            <button onClick={() => window.location.assign('/')} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50">
              Go to Timetablz
            </button>
            <button onClick={signOut} className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700">
              Sign out
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-6 px-6 py-4">
          <div className="flex items-baseline gap-2">
            <span className="text-[17px] font-bold tracking-tight">Timetablz</span>
            <span className="rounded bg-neutral-900 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-white">Admin</span>
          </div>
          <nav className="flex gap-1 text-sm" aria-label="Admin sections">
            {[
              ['dashboard', 'Dashboard'],
              ['accounts', 'Accounts'],
              ['outreach', 'Outreach'],
              ['rules', 'Rule reading'],
            ].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setView(id)}
                aria-current={view === id ? 'page' : undefined}
                className={`rounded-md px-3 py-1.5 font-medium ${view === id ? 'bg-neutral-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
              >
                {label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-4 text-sm">
            <span className="text-slate-500">{user.email}</span>
            <button onClick={signOut} className="font-medium text-slate-700 hover:text-slate-900">
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {view === 'dashboard' ? <Dashboard /> : view === 'rules' ? <AdminRuleEvents /> : view === 'outreach' ? <AdminOutreach notice={outreachNotice} /> : <Accounts />}
      </main>
    </div>
  )
}

const FILTERS = [
  ['all', 'All'],
  ['free', 'Free period'],
  ['active', 'Paid'],
  ['grace', 'Grace'],
  ['locked', 'Locked'],
]

function Dashboard() {
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('all')
  const [error, setError] = useState(null)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    api.admin.stats().then(setStats).catch((e) => setError(e.message))
  }, [refresh])

  const inr = (n) => `₹${Number(n ?? 0).toLocaleString('en-IN')}`

  return (
    <div className="flex flex-col gap-8">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Schools" value={stats?.schools} hint={stats ? `${stats.accounts} user accounts` : ''} />
        <Stat
          label="Paying"
          value={stats ? stats.paying.pro + stats.paying.business : null}
          hint={stats ? `${stats.paying.pro} Pro · ${stats.paying.business} Business` : ''}
        />
        <Stat
          label="On free period"
          value={stats?.by_status.free}
          hint={stats ? `${stats.free_ending_within_3_days} ending within 3 days` : ''}
        />
        <Stat
          label="Grace / locked"
          value={stats ? `${stats.by_status.grace} / ${stats.by_status.locked}` : null}
          hint="Need to renew or upgrade"
        />
        <Stat label="Revenue this month" value={stats ? inr(stats.revenue_this_month_inr) : null} hint="From issued invoices" />
        <Stat label="Revenue to date" value={stats ? inr(stats.revenue_total_inr) : null} hint={stats ? `${stats.invoices} invoices` : ''} />
        <Stat label="Open offers" value={stats?.open_offers} hint="Custom plans waiting for payment" />
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter schools by status">
        {FILTERS.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setFilter(id)}
            aria-pressed={filter === id}
            className={`rounded-full border px-3 py-1 text-sm ${filter === id ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'}`}
          >
            {label}
          </button>
        ))}
        <button onClick={() => setRefresh((n) => n + 1)} className="ml-auto text-sm text-slate-500 underline underline-offset-2">
          Refresh numbers
        </button>
      </div>

      <AdminTab statusFilter={filter} />
    </div>
  )
}

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight">{value ?? '…'}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

function Accounts() {
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState('')
  const [error, setError] = useState(null)

  function load(query = q) {
    api.admin.accounts(query).then(setRows).catch((e) => setError(e.message))
  }
  useEffect(() => {
    load('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Accounts</h2>
          <p className="mt-1 text-sm text-slate-500">Every user, and the schools they own or were invited to.</p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            load(q)
          }}
          className="flex gap-2"
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name or email"
            aria-label="Search accounts"
            className="w-60 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <button className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-50">Search</button>
        </form>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2.5 font-medium">Account</th>
              <th className="px-4 py-2.5 font-medium">Sign-in</th>
              <th className="px-4 py-2.5 font-medium">Owns</th>
              <th className="px-4 py-2.5 font-medium">Member of</th>
            </tr>
          </thead>
          <tbody>
            {rows == null && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-400">Loading…</td>
              </tr>
            )}
            {rows?.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-400">No accounts found.</td>
              </tr>
            )}
            {rows?.map((a) => (
              <tr key={a.id} className="border-t border-slate-100">
                <td className="px-4 py-3">
                  <p className="font-medium">{a.name || '-'}</p>
                  <p className="text-xs text-slate-500">{a.email}</p>
                </td>
                <td className="px-4 py-3 text-slate-600">{a.google ? 'Google' : 'Email'}</td>
                <td className="px-4 py-3 text-slate-600">{a.owns.length ? a.owns.join(', ') : '-'}</td>
                <td className="px-4 py-3 text-slate-600">{a.member_of.length ? a.member_of.join(', ') : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
