import { useEffect, useState } from 'react'
import { api } from '../api'
import TeamTab from './TeamTab'

/**
 * Settings, opened from the header (left of Sign out). Three sections in a
 * left-hand list, same layout idea as TimetableMaster's settings page:
 *
 *   - School profile: name, type, board, codes, head of institution,
 *     contact details and address. Read view with an Edit button, like
 *     TimetableMaster's Institute Information. Admin-only to change.
 *   - My account: display name (editable), email (fixed - it's the login),
 *     and a button that emails a password reset link.
 *   - Team: what used to be the Team tab in the header (admins only).
 *
 * Grade order isn't here because the sidebar already has a Reorder mode
 * for it, right next to the grades themselves.
 */
export default function SettingsTab({
  user,
  onUserUpdated,
  school,
  onRenameSchool,
  onUpdateInstitutionType,
  onSaveProfile,
  isAdmin,
  members,
  invites,
  onReloadTeam,
  initialSection = 'school',
}) {
  const sections = [
    { id: 'school', label: 'School profile', hint: 'Details, contact, address' },
    { id: 'account', label: 'My account', hint: 'Name, email, password' },
    ...(isAdmin ? [{ id: 'team', label: 'Team', hint: 'Who has access' }] : []),
  ]
  const [section, setSection] = useState(
    sections.some((s) => s.id === initialSection) ? initialSection : 'school'
  )

  return (
    <div className="flex max-w-5xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Settings</h2>
        <p className="mt-1 text-sm text-slate-500">Manage your school, your account and who has access.</p>
      </div>

      <div className="flex flex-col gap-6 md:flex-row">
        <nav className="flex flex-none flex-row gap-1 md:w-56 md:flex-col">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              className={`rounded-md px-3 py-2 text-left ${
                section === s.id ? 'bg-white shadow-sm ring-1 ring-slate-200' : 'hover:bg-slate-100'
              }`}
            >
              <span className={`block text-sm font-medium ${section === s.id ? 'text-slate-900' : 'text-slate-600'}`}>
                {s.label}
              </span>
              <span className="hidden text-xs text-slate-400 md:block">{s.hint}</span>
            </button>
          ))}
        </nav>

        <div className="min-w-0 flex-1">
          {section === 'school' && (
            <SchoolProfile
              school={school}
              isAdmin={isAdmin}
              onRename={onRenameSchool}
              onUpdateInstitutionType={onUpdateInstitutionType}
              onSaveProfile={onSaveProfile}
            />
          )}
          {section === 'account' && <MyAccount user={user} onUserUpdated={onUserUpdated} />}
          {section === 'team' && isAdmin && (
            <div className="rounded-lg border border-slate-200 bg-white p-6">
              <TeamTab schoolId={school.id} members={members} invites={invites} onReload={onReloadTeam} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Card({ title, description, children }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h3 className="text-base font-semibold">{title}</h3>
      {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      <div className="mt-5 flex flex-col gap-5">{children}</div>
    </section>
  )
}

function Field({ label, htmlFor, help, children }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 block text-xs font-medium text-slate-500">
        {label}
      </label>
      {children}
      {help && <p className="mt-1.5 text-xs text-slate-400">{help}</p>}
    </div>
  )
}

const inputCls =
  'w-full max-w-md rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none disabled:bg-slate-50 disabled:text-slate-500'
const primaryBtn =
  'rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50'

const BOARD_SUGGESTIONS = {
  school: ['CBSE', 'ICSE / ISC', 'State Board', 'IB', 'Cambridge (IGCSE)', 'NIOS'],
  college: ['Autonomous', 'University affiliated', 'Deemed university', 'State university', 'Central university'],
}
const HEAD_TITLES = ['Principal', 'Headmaster', 'Headmistress', 'Director', 'Dean', 'Vice Chancellor']
const MEDIUMS = ['English', 'Hindi', 'Malayalam', 'Tamil', 'Kannada', 'Telugu', 'Marathi', 'Bengali', 'Gujarati']
const INDIAN_STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa', 'Gujarat', 'Haryana',
  'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
  'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana',
  'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Andaman and Nicobar Islands', 'Chandigarh',
  'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
]
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const PROFILE_KEYS = [
  'board', 'affiliation_number', 'udise_code', 'established_year', 'head_name', 'head_title', 'medium',
  'academic_year_start_month', 'student_count', 'website', 'email', 'phone', 'address', 'city', 'state',
  'country', 'postal_code', 'description',
]
const NUMBER_KEYS = ['established_year', 'academic_year_start_month', 'student_count']

function profileToForm(school) {
  const p = school.profile || {}
  const form = { name: school.name }
  for (const k of PROFILE_KEYS) form[k] = p[k] == null ? '' : String(p[k])
  if (!form.country) form.country = 'India'
  if (!form.head_title) form.head_title = 'Principal'
  return form
}

function formToProfile(form) {
  const out = {}
  for (const k of PROFILE_KEYS) {
    const v = (form[k] ?? '').trim()
    if (!v) continue
    out[k] = NUMBER_KEYS.includes(k) ? Number(v) : v
  }
  // The title field is pre-filled with "Principal"; don't save it on its own.
  if (!out.head_name) delete out.head_title
  return out
}

function validate(form) {
  const errors = {}
  if (!form.name.trim()) errors.name = 'Enter a name'
  const year = form.established_year.trim()
  if (year && (!/^\d{4}$/.test(year) || Number(year) < 1800 || Number(year) > new Date().getFullYear())) {
    errors.established_year = 'Enter a 4-digit year'
  }
  const count = form.student_count.trim()
  if (count && !/^\d+$/.test(count)) errors.student_count = 'Enter a whole number'
  const email = form.email.trim()
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Enter a valid email'
  const phone = form.phone.trim()
  if (phone && !/^[+\d][\d\s-]{6,}$/.test(phone)) errors.phone = 'Enter a valid phone number'
  const pin = form.postal_code.trim()
  if (pin && form.country.trim().toLowerCase() === 'india' && !/^\d{6}$/.test(pin)) {
    errors.postal_code = 'Indian PIN codes have 6 digits'
  }
  return errors
}

/**
 * Settings > School profile. Read view by default (label / value pairs,
 * "Not provided" for blanks, like TimetableMaster's Institute Information),
 * with an Edit button for admins that turns the same groups into a form.
 * Name and type save through their existing endpoints; everything else is
 * one PUT /schools/{id}/profile.
 */
function SchoolProfile({ school, isAdmin, onRename, onUpdateInstitutionType, onSaveProfile }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(() => profileToForm(school))
  const [type, setType] = useState(school.institution_type === 'college' ? 'college' : 'school')
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [savedAt, setSavedAt] = useState(null)

  useEffect(() => {
    setEditing(false)
    setErrors({})
    setSaveError(null)
    setSavedAt(null)
  }, [school.id])

  useEffect(() => {
    if (!editing) {
      setForm(profileToForm(school))
      setType(school.institution_type === 'college' ? 'college' : 'school')
    }
  }, [school, editing])

  const isCollege = type === 'college'
  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    if (errors[key]) setErrors((er) => ({ ...er, [key]: undefined }))
  }

  async function save(e) {
    e.preventDefault()
    const found = validate(form)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    setSaving(true)
    setSaveError(null)
    try {
      if (form.name.trim() !== school.name) await onRename(form.name.trim())
      const currentType = school.institution_type === 'college' ? 'college' : 'school'
      if (type !== currentType) await onUpdateInstitutionType(type)
      await onSaveProfile(formToProfile(form))
      setEditing(false)
      setSavedAt(Date.now())
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const p = school.profile || {}
  const savedType = school.institution_type === 'college' ? 'college' : 'school'
  const codeLabel = (isCollege || (!editing && savedType === 'college')) ? 'AISHE code' : 'UDISE+ code'
  const boardLabel = (editing ? isCollege : savedType === 'college') ? 'Affiliation / university' : 'Board'

  if (!editing) {
    const month = p.academic_year_start_month ? MONTHS[p.academic_year_start_month - 1] : null
    const head = p.head_name ? `${p.head_name}${p.head_title ? ` (${p.head_title})` : ''}` : null
    const addressLine = [p.address, p.city, p.state, p.postal_code, p.country].filter(Boolean).join(', ')
    return (
      <div className="flex flex-col gap-6">
        <ViewSection
          title={savedType === 'college' ? 'College information' : 'School information'}
          action={
            isAdmin && (
              <button
                onClick={() => setEditing(true)}
                className="flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
                </svg>
                Edit
              </button>
            )
          }
          note={
            savedAt ? 'Saved.' : !isAdmin ? 'Only admins can change these details.' : null
          }
          rows={[
            ['Name', school.name],
            ['Type', savedType === 'college' ? 'College' : 'School'],
            [boardLabel, p.board],
            ['Affiliation number', p.affiliation_number],
            [codeLabel, p.udise_code],
            ['Established', p.established_year],
            ['Medium of instruction', p.medium],
            ['Number of students', p.student_count != null ? Number(p.student_count).toLocaleString('en-IN') : null],
          ]}
        />
        <ViewSection
          title="Academic year and leadership"
          rows={[
            ['Academic year starts in', month],
            ['Head of institution', head],
          ]}
        />
        <ViewSection
          title="Contact"
          rows={[
            ['Email', p.email],
            ['Phone', p.phone],
            ['Website', p.website],
            ['Address', addressLine || null],
          ]}
        />
        <ViewSection title="About" rows={[['Description', p.description]]} wide />
      </div>
    )
  }

  return (
    <form onSubmit={save} noValidate className="flex flex-col gap-6">
      <EditSection title={isCollege ? 'College information' : 'School information'}>
        <Input label={isCollege ? 'College name' : 'School name'} id="sp-name" value={form.name} onChange={set('name')} error={errors.name} maxLength={120} span />
        <div className="sm:col-span-2">
          <span className="mb-1.5 block text-xs font-medium text-slate-500">Type</span>
          <div className="flex max-w-xs gap-2">
            {[
              { value: 'school', label: 'School' },
              { value: 'college', label: 'College' },
            ].map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setType(opt.value)}
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium ${
                  type === opt.value ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-slate-400">
            Only changes wording and which optional fields show up (e.g. credits and lab batches for colleges). No data is removed.
          </p>
        </div>
        <Input label={isCollege ? 'Affiliation / university' : 'Board'} id="sp-board" value={form.board} onChange={set('board')} list="sp-board-list" maxLength={80} placeholder={isCollege ? 'University of Kerala' : 'CBSE'} />
        <datalist id="sp-board-list">
          {BOARD_SUGGESTIONS[type].map((b) => <option key={b} value={b} />)}
        </datalist>
        <Input label="Affiliation number" id="sp-aff" value={form.affiliation_number} onChange={set('affiliation_number')} maxLength={60} placeholder={isCollege ? '' : '930123'} />
        <Input
          label={isCollege ? 'AISHE code' : 'UDISE+ code'}
          id="sp-code"
          value={form.udise_code}
          onChange={set('udise_code')}
          maxLength={30}
          help={isCollege ? 'From the AISHE portal, e.g. C-12345' : '11-digit code from the UDISE+ portal'}
        />
        <Input label="Year established" id="sp-year" value={form.established_year} onChange={set('established_year')} error={errors.established_year} inputMode="numeric" maxLength={4} placeholder="1998" />
        <Input label="Medium of instruction" id="sp-medium" value={form.medium} onChange={set('medium')} list="sp-medium-list" maxLength={60} placeholder="English" />
        <datalist id="sp-medium-list">
          {MEDIUMS.map((m) => <option key={m} value={m} />)}
        </datalist>
        <Input label="Number of students" id="sp-students" value={form.student_count} onChange={set('student_count')} error={errors.student_count} inputMode="numeric" maxLength={6} placeholder="1200" />
      </EditSection>

      <EditSection title="Academic year and leadership">
        <div>
          <label htmlFor="sp-month" className="mb-1.5 block text-xs font-medium text-slate-500">Academic year starts in</label>
          <select id="sp-month" value={form.academic_year_start_month} onChange={set('academic_year_start_month')} className={inputCls}>
            <option value="">Not set</option>
            {MONTHS.map((m, i) => <option key={m} value={String(i + 1)}>{m}</option>)}
          </select>
          <p className="mt-1.5 text-xs text-slate-400">Most Indian schools start in April or June.</p>
        </div>
        <div />
        <Input label="Head of institution" id="sp-head" value={form.head_name} onChange={set('head_name')} maxLength={100} placeholder="Dr. Meera Nair" />
        <Input label="Their title" id="sp-head-title" value={form.head_title} onChange={set('head_title')} list="sp-title-list" maxLength={60} />
        <datalist id="sp-title-list">
          {HEAD_TITLES.map((t) => <option key={t} value={t} />)}
        </datalist>
      </EditSection>

      <EditSection title="Contact">
        <Input label="Email" id="sp-email" type="email" value={form.email} onChange={set('email')} error={errors.email} maxLength={200} placeholder="office@school.edu.in" />
        <Input label="Phone" id="sp-phone" type="tel" value={form.phone} onChange={set('phone')} error={errors.phone} maxLength={40} placeholder="+91 471 234 5678" />
        <Input label="Website" id="sp-web" value={form.website} onChange={set('website')} maxLength={200} placeholder="www.school.edu.in" span />
        <Input label="Address" id="sp-address" value={form.address} onChange={set('address')} maxLength={300} placeholder="Street, area" span />
        <Input label="City" id="sp-city" value={form.city} onChange={set('city')} maxLength={80} />
        <Input label="State" id="sp-state" value={form.state} onChange={set('state')} list="sp-state-list" maxLength={80} />
        <datalist id="sp-state-list">
          {INDIAN_STATES.map((st) => <option key={st} value={st} />)}
        </datalist>
        <Input label="PIN / postal code" id="sp-pin" value={form.postal_code} onChange={set('postal_code')} error={errors.postal_code} inputMode="numeric" maxLength={20} />
        <Input label="Country" id="sp-country" value={form.country} onChange={set('country')} maxLength={80} />
      </EditSection>

      <EditSection title="About">
        <div className="sm:col-span-2">
          <label htmlFor="sp-desc" className="mb-1.5 block text-xs font-medium text-slate-500">Description</label>
          <textarea
            id="sp-desc"
            value={form.description}
            onChange={set('description')}
            rows={3}
            maxLength={1000}
            placeholder="A short note about your school"
            className={`${inputCls} max-w-none resize-y`}
          />
        </div>
      </EditSection>

      <div className="sticky bottom-0 -mx-1 flex items-center gap-3 bg-slate-50/95 px-1 py-3">
        <button type="submit" disabled={saving} className={primaryBtn}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={() => {
            setEditing(false)
            setErrors({})
            setSaveError(null)
          }}
          className="rounded-md px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100"
        >
          Cancel
        </button>
        {Object.keys(errors).some((k) => errors[k]) && (
          <span className="text-xs text-red-600">Fix the highlighted fields first.</span>
        )}
        {saveError && <span className="text-xs text-red-600">{saveError}</span>}
      </div>
    </form>
  )
}

function ViewSection({ title, rows, action, note, wide }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-6 py-4">
        <div>
          <h3 className="text-base font-semibold">{title}</h3>
          {note && <p className="mt-0.5 text-xs text-slate-500">{note}</p>}
        </div>
        {action}
      </div>
      <dl className={`grid gap-x-10 gap-y-5 px-6 py-5 ${wide ? '' : 'sm:grid-cols-2'}`}>
        {rows.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-xs font-medium text-slate-500">{label}</dt>
            <dd className={`mt-1 break-words text-sm ${value == null || value === '' ? 'text-slate-400' : 'text-slate-900'}`}>
              {value == null || value === '' ? 'Not provided' : value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function EditSection({ title, children }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-6 py-4">
        <h3 className="text-base font-semibold">{title}</h3>
      </div>
      <div className="grid gap-x-6 gap-y-4 px-6 py-5 sm:grid-cols-2">{children}</div>
    </section>
  )
}

function Input({ label, id, error, help, span, className, ...props }) {
  return (
    <div className={span ? 'sm:col-span-2' : undefined}>
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-slate-500">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? 'true' : undefined}
        className={`${inputCls} max-w-none ${error ? 'border-red-400 focus:border-red-500' : ''}`}
        {...props}
      />
      {error ? (
        <p className="mt-1.5 text-xs text-red-600">{error}</p>
      ) : help ? (
        <p className="mt-1.5 text-xs text-slate-400">{help}</p>
      ) : null}
    </div>
  )
}

function MyAccount({ user, onUserUpdated }) {
  const [name, setName] = useState(user?.name || '')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [resetState, setResetState] = useState('idle') // idle | sending | sent | error

  const changed = name.trim() && name.trim() !== (user?.name || '')

  async function save(e) {
    e.preventDefault()
    if (!changed) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const updated = await api.updateMe({ name: name.trim() })
      onUserUpdated(updated)
      setMessage('Saved')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function sendReset() {
    setResetState('sending')
    try {
      await api.forgotPassword(user.email)
      setResetState('sent')
    } catch {
      setResetState('error')
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card title="My account" description="Your personal details. These aren't shared outside your school's team.">
        <form onSubmit={save} className="flex flex-col gap-3">
          <Field label="Your name" htmlFor="settings-user-name">
            <input
              id="settings-user-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              className={inputCls}
            />
          </Field>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={!changed || saving} className={primaryBtn}>
              {saving ? 'Saving…' : 'Save name'}
            </button>
            {message && <span className="text-xs text-slate-500">{message}</span>}
            {error && <span className="text-xs text-red-600">{error}</span>}
          </div>
        </form>

        <Field label="Email" help="This is how you sign in, so it can't be changed here.">
          <input value={user?.email || ''} disabled className={inputCls} />
        </Field>
      </Card>

      <Card
        title="Password"
        description="We'll email you a link to set a new password. If you sign in with Google, this lets you add a password too."
      >
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={sendReset}
            disabled={resetState === 'sending' || resetState === 'sent'}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {resetState === 'sending' ? 'Sending…' : resetState === 'sent' ? 'Link sent' : 'Email me a reset link'}
          </button>
          {resetState === 'sent' && (
            <span className="text-xs text-slate-500">Check {user.email}. The link expires in an hour.</span>
          )}
          {resetState === 'error' && (
            <span className="text-xs text-red-600">Couldn't send it right now. Try again in a minute.</span>
          )}
        </div>
      </Card>
    </div>
  )
}
