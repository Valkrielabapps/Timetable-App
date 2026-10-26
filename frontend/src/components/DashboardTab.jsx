import { useState } from 'react'
import { api } from '../api'
import { useFrozenStatus, useTimetables, useVersionActions } from '../hooks/useSchoolData'
import { pickVersions } from '../lib/versions'
import { sortGradeKeys } from './Sidebar'

/**
 * The landing tab once a school has at least one section: everything about
 * the school's timetables in one place. Replaces OverviewTab, which only
 * walked one section through setup.
 *
 *   - a greeting and the school at a glance (sections, teachers, subjects,
 *     rules, teaching periods a week)
 *   - setup progress, only while something required is still missing
 *   - every timetable version generated, newest first, with Open (latest)
 *     and Excel/PDF export
 *   - every section, grouped by grade, with how much of its weekly plan is
 *     filled in and shortcuts into its plan or timetable
 *
 * Purely reads App.jsx's already-loaded state plus the cached timetable
 * list (same React Query key as TimetableTab and App.jsx, so no extra
 * request). Versions have no created_at, so they're numbered by id order.
 */
export default function DashboardTab({
  user,
  school,
  classGroups,
  teachers,
  subjects,
  constraints,
  periods,
  allRequirements,
  progress,
  onNavigate,
  onOpenSection,
  readOnly = false,
}) {
  const { data: timetables = [], isLoading: timetablesLoading } = useTimetables(school.id)
  const versions = [...timetables].sort((a, b) => b.id - a.id)
  const latestId = versions[0]?.id ?? null
  const { current } = pickVersions(timetables)
  const actions = useVersionActions(school.id)
  const { data: frozenList = [] } = useFrozenStatus(school.id, current?.id)
  // Versions frozen sections are kept from can't be deleted until unfrozen.
  const frozenFrom = new Map()
  for (const f of frozenList) {
    if (f.frozen && f.frozen_from_timetable_id) {
      const cg = classGroups.find((c) => c.id === f.class_group_id)
      if (cg) frozenFrom.set(f.frozen_from_timetable_id, [...(frozenFrom.get(f.frozen_from_timetable_id) ?? []), cg])
    }
  }
  const latestDraftId = versions.find((t) => t.status === 'draft')?.id ?? null

  const teachingPeriods = periods.filter((p) => !p.is_break).length
  const enforcedRules = constraints.filter((c) => c.enforced !== false).length

  const firstName = (user?.name || '').trim().split(/\s+/)[0]
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })

  const stats = [
    { label: 'Sections', value: classGroups.length, onClick: null },
    { label: 'Teachers', value: teachers.length, onClick: () => onNavigate('entry', 'teachers') },
    { label: 'Subjects', value: subjects.length, onClick: () => onNavigate('entry', 'subjects') },
    {
      label: 'Rules',
      value: constraints.length,
      hint: constraints.length > 0 && enforcedRules < constraints.length ? `${enforcedRules} enforced` : null,
      onClick: () => onNavigate('constraints'),
    },
    { label: 'Periods a week', value: teachingPeriods, onClick: () => onNavigate('entry', 'setup') },
  ]

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            {greeting}
            {firstName ? `, ${firstName}` : ''}
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {school.name} · {today}
          </p>
        </div>
        {!readOnly && (
          <button
            onClick={() => onNavigate('timetable')}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
          >
            {latestDraftId ? 'Open timetable' : 'Build the timetable'}
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {stats.map((s) => {
          const Tag = s.onClick ? 'button' : 'div'
          return (
            <Tag
              key={s.label}
              onClick={s.onClick || undefined}
              className={`rounded-lg border border-slate-200 bg-white p-4 text-left ${
                s.onClick ? 'transition-colors hover:border-slate-300 hover:bg-slate-50' : ''
              }`}
            >
              <p className="text-xs font-medium text-slate-500">{s.label}</p>
              <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight">{s.value}</p>
              {s.hint && <p className="mt-0.5 text-xs text-amber-700">{s.hint}</p>}
            </Tag>
          )
        })}
      </div>

      {progress.loaded && !progress.allRequiredDone && (
        <SetupCard progress={progress} onNavigate={onNavigate} />
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <section className="rounded-lg border border-slate-200 bg-white lg:col-span-2">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
            <h3 className="text-sm font-semibold">Timetable versions</h3>
            <span className="text-xs text-slate-400">{versions.length} total</span>
          </div>
          {timetablesLoading ? (
            <p className="px-5 py-6 text-sm text-slate-400">Loading…</p>
          ) : versions.length === 0 ? (
            <div className="px-5 py-8 text-center">
              <p className="text-sm font-medium text-slate-700">No timetable yet</p>
              <p className="mt-1 text-xs text-slate-500">
                Each time you generate, a new version appears here. One version covers every section.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {versions.map((t, i) => (
                <VersionRow
                  key={t.id}
                  timetable={t}
                  number={t.version_number ?? versions.length - i}
                  isLatest={t.id === latestId}
                  isCurrent={t.id === current?.id}
                  frozenSections={frozenFrom.get(t.id) ?? []}
                  readOnly={readOnly}
                  onOpen={async () => {
                    if (t.id !== current?.id) await actions.open(t.id)
                    onNavigate('timetable')
                  }}
                  onRename={(name) => actions.rename(t.id, name)}
                  onDelete={() => actions.remove(t.id)}
                />
              ))}
            </ul>
          )}
          {versions.length > 0 && (
            <p className="border-t border-slate-100 px-5 py-2.5 text-xs text-slate-500">
              The newest 5 versions are kept. Older ones are removed when you generate, except the one you&rsquo;re
              working from and any a frozen section is kept from.
            </p>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white lg:col-span-3">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
            <h3 className="text-sm font-semibold">Sections</h3>
            <span className="text-xs text-slate-400">{classGroups.length} total</span>
          </div>
          <SectionsList
            classGroups={classGroups}
            gradeOrder={school.grade_order}
            allRequirements={allRequirements}
            teachingPeriods={teachingPeriods}
            hasTimetable={Boolean(latestDraftId)}
            onOpenSection={onOpenSection}
          />
        </section>
      </div>
    </div>
  )
}

function SetupCard({ progress, onNavigate }) {
  const { steps, requiredSteps, doneRequiredCount, currentStep } = progress
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Finish setting up</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {doneRequiredCount} of {requiredSteps.length} required steps done
          </p>
        </div>
        {currentStep && (
          <button
            onClick={() => onNavigate(currentStep.tab, currentStep.subView)}
            className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700"
          >
            Next: {currentStep.title}
          </button>
        )}
      </div>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-neutral-900 transition-all"
          style={{ width: `${(doneRequiredCount / requiredSteps.length) * 100}%` }}
        />
      </div>
      <ol className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {steps.map((step) => (
          <li key={step.key}>
            <button
              onClick={() => onNavigate(step.tab, step.subView)}
              className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-slate-50"
            >
              <span
                className={`flex h-5 w-5 flex-none items-center justify-center rounded-full text-[10px] font-semibold ${
                  step.done ? 'bg-neutral-900 text-white' : 'border border-slate-300 text-slate-400'
                }`}
              >
                {step.done ? '✓' : ''}
              </span>
              <span className={step.done ? 'text-slate-400 line-through decoration-slate-300' : 'text-slate-700'}>
                {step.title}
              </span>
              {step.optional && <span className="text-[10px] uppercase tracking-wide text-slate-400">optional</span>}
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}

const STATUS_STYLES = {
  draft: { label: 'Ready', cls: 'bg-slate-100 text-slate-700' },
  published: { label: 'Published', cls: 'bg-slate-100 text-slate-700' },
  generating: { label: 'Generating…', cls: 'bg-blue-50 text-blue-700' },
  failed: { label: 'Failed', cls: 'bg-red-50 text-red-700' },
  archived: { label: 'Archived', cls: 'bg-slate-100 text-slate-500' },
}

function VersionRow({ timetable, number, isLatest, isCurrent, frozenSections, readOnly, onOpen, onRename, onDelete }) {
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [renaming, setRenaming] = useState(false)
  const [draftName, setDraftName] = useState(timetable.name ?? '')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const status = STATUS_STYLES[timetable.status] || { label: timetable.status, cls: 'bg-slate-100 text-slate-600' }
  const usable = timetable.status === 'draft' || timetable.status === 'published'
  const canExport = usable
  const locked = frozenSections.length > 0

  async function run(kind, fn) {
    setBusy(kind)
    setError(null)
    try {
      await fn()
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setBusy(null)
    }
  }

  async function exportAs(format) {
    await run(format, () => api.downloadTimetableExport(timetable.id, format))
  }

  const frozenNames = frozenSections.map((cg) => (cg.grade ? `${cg.grade} - ${cg.name}` : cg.name))

  return (
    <li className={`px-5 py-3 ${isCurrent ? 'bg-slate-50' : ''}`}>
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          {renaming ? (
            <form
              onSubmit={async (e) => {
                e.preventDefault()
                if (await run('rename', () => onRename(draftName))) setRenaming(false)
              }}
              className="flex items-center gap-1.5"
            >
              <input
                autoFocus
                value={draftName}
                maxLength={80}
                onChange={(e) => setDraftName(e.target.value)}
                placeholder={`Version ${number}, e.g. Grades 1-5 approved`}
                aria-label="Version name"
                className="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm focus:border-neutral-900 focus:outline-none"
              />
              <button disabled={busy === 'rename'} className="rounded-md bg-neutral-900 px-2 py-1 text-xs font-medium text-white">
                Save
              </button>
              <button type="button" onClick={() => setRenaming(false)} className="px-1 text-xs text-slate-500">
                Cancel
              </button>
            </form>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">Version {number}</span>
              {timetable.name && <span className="truncate text-sm text-slate-600">· {timetable.name}</span>}
              {isCurrent && (
                <span className="rounded-full bg-neutral-900 px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-white">
                  Current
                </span>
              )}
              {isLatest && !isCurrent && (
                <span className="rounded-full border border-slate-200 px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-slate-500">
                  Latest
                </span>
              )}
            </div>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${status.cls}`}>{status.label}</span>
            {timetable.created_at && (
              <span className="text-[11px] text-slate-400">{new Date(timetable.created_at).toLocaleString()}</span>
            )}
            {locked && <span className="text-[11px] text-sky-700">❄ {frozenNames.length} frozen from this version</span>}
          </div>
        </div>
        <div className="flex flex-none flex-wrap items-center justify-end gap-1.5">
          {usable && (!readOnly || isCurrent) && (
            <button
              onClick={() => run('open', onOpen)}
              disabled={busy != null}
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {busy === 'open' ? '…' : 'Open'}
            </button>
          )}
          {canExport && (
            <>
              <button
                onClick={() => exportAs('xlsx')}
                disabled={busy != null}
                className="rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 disabled:opacity-50"
              >
                {busy === 'xlsx' ? '…' : 'Excel'}
              </button>
              <button
                onClick={() => exportAs('pdf')}
                disabled={busy != null}
                className="rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 disabled:opacity-50"
              >
                {busy === 'pdf' ? '…' : 'PDF'}
              </button>
            </>
          )}
          {!readOnly && usable && !renaming && (
            <button
              onClick={() => {
                setDraftName(timetable.name ?? '')
                setRenaming(true)
              }}
              className="rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100"
            >
              Rename
            </button>
          )}
          {!readOnly && timetable.status !== 'generating' && (
            <button
              onClick={() => setConfirmDelete(true)}
              disabled={busy != null}
              title={locked ? `Frozen from this version: ${frozenNames.join(', ')}` : undefined}
              className="rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
            >
              Delete
            </button>
          )}
        </div>
      </div>
      {confirmDelete && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">
          {locked ? (
            <span className="flex-1">
              {frozenNames.join(', ')} {frozenNames.length === 1 ? 'is' : 'are'} frozen from this version. Unfreeze{' '}
              {frozenNames.length === 1 ? 'it' : 'them'} on the Timetable tab before deleting it.
            </span>
          ) : (
            <>
              <span className="flex-1">
                Delete Version {number}
                {isCurrent ? '? You\u2019ll switch to the newest version left.' : '? This can\u2019t be undone.'}
              </span>
              <button
                onClick={async () => {
                  if (await run('delete', onDelete)) setConfirmDelete(false)
                }}
                disabled={busy === 'delete'}
                className="rounded-md bg-red-600 px-2 py-1 font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {busy === 'delete' ? 'Deleting…' : 'Delete'}
              </button>
            </>
          )}
          <button onClick={() => setConfirmDelete(false)} className="px-1 font-medium text-red-900 underline">
            {locked ? 'OK' : 'Cancel'}
          </button>
        </div>
      )}
      {timetable.status === 'failed' && (timetable.error_explanation || timetable.error_message) && (
        <p className="mt-1.5 line-clamp-2 text-xs text-slate-500">
          {timetable.error_explanation || timetable.error_message}
        </p>
      )}
      {error && <p className="mt-1.5 text-xs text-red-600">{error}</p>}
    </li>
  )
}

function SectionsList({ classGroups, gradeOrder, allRequirements, teachingPeriods, hasTimetable, onOpenSection }) {
  if (classGroups.length === 0) {
    return <p className="px-5 py-6 text-sm text-slate-500">No sections yet. Add one from the sidebar.</p>
  }

  const byGrade = {}
  for (const cg of classGroups) {
    const key = cg.grade || 'Ungrouped'
    ;(byGrade[key] ||= []).push(cg)
  }
  const grades = sortGradeKeys(Object.keys(byGrade), gradeOrder)

  return (
    <div className="max-h-[480px] divide-y divide-slate-100 overflow-y-auto">
      {grades.map((grade) => (
        <div key={grade} className="px-5 py-3">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{grade}</p>
          <ul className="flex flex-col">
            {byGrade[grade]
              .slice()
              .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
              .map((cg) => {
                const reqs = allRequirements.filter((r) => r.class_group_id === cg.id)
                const planned = reqs.reduce((sum, r) => sum + (r.periods_per_week || 0), 0)
                const pct = teachingPeriods > 0 ? Math.min(100, Math.round((planned / teachingPeriods) * 100)) : 0
                return (
                  <li key={cg.id} className="flex items-center gap-3 rounded-md py-1.5">
                    <span className="w-28 flex-none truncate text-sm font-medium">Section {cg.name}</span>
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <div className="h-full rounded-full bg-neutral-900" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="w-24 flex-none text-right text-xs tabular-nums text-slate-500">
                        {reqs.length === 0 ? 'No plan yet' : `${planned}/${teachingPeriods} periods`}
                      </span>
                    </div>
                    <div className="flex flex-none gap-1">
                      <button
                        onClick={() => onOpenSection(cg.id, 'plan')}
                        className="rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100"
                      >
                        Plan
                      </button>
                      <button
                        onClick={() => onOpenSection(cg.id, 'timetable')}
                        disabled={!hasTimetable}
                        title={hasTimetable ? undefined : 'Generate a timetable first'}
                        className="rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Timetable
                      </button>
                    </div>
                  </li>
                )
              })}
          </ul>
        </div>
      ))}
    </div>
  )
}
