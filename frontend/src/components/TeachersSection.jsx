import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '../api'
import BulkImportPanel from './BulkImportPanel'
import { confirmDialog } from './confirmDialog'
import { useElectiveBlocks, useTimetable, useTimetables } from '../hooks/useSchoolData'
import { compareNames, loadChoice, matchesSearch, rankMatches, saveChoice, sortByName } from '../sorting'

const SORTS = [
  ['name', 'Name (A–Z)'],
  ['name-desc', 'Name (Z–A)'],
  ['load-desc', 'Periods/week (most first)'],
  ['load-asc', 'Periods/week (fewest first)'],
  ['subjects', 'Subjects (most first)'],
  ['grades', 'Grades taught'],
]
const SORT_KEY = 'timetablz.teachers.sort'

/**
 * "Who teaches what" — one row per teacher, their subjects shown as
 * removable chips with a "+ Add" picker for the rest. This is the
 * teacher-centric mirror of the subject-to-teacher assignment that used
 * to live inline in the (now-removed) combined subjects/teachers table —
 * moved here since "which subjects does this teacher cover" is naturally
 * a question about the teacher, not something that should require
 * finding them in every relevant subject's own dropdown one at a time.
 */
// Distinct grade labels across every section, in natural order - "Grade 2"
// before "Grade 10", which a plain string sort gets wrong. Shared by the
// inline per-teacher picker and AddTeacherModal so the two can't drift.
function distinctGrades(classGroups) {
  return [...new Set(classGroups.map((cg) => cg.grade).filter(Boolean))].sort(compareNames)
}

/**
 * Periods each teacher actually has in the timetable on screen - what the
 * generator gave them, not only what was pinned on section plans. A class
 * left on "any qualified teacher" lands on somebody; this is where it shows.
 * Counted once per period, as the teacher or as the assistant. Null when
 * there is no generated timetable to count from.
 */
function useRealLoad(schoolId) {
  const { data: list = [] } = useTimetables(schoolId)
  const latestId = list.length ? list.reduce((a, b) => (b.id > a.id ? b : a)).id : null
  const { data: timetable } = useTimetable(latestId)
  return useMemo(() => {
    if (!timetable || timetable.status !== 'draft') return null
    const periods = new Map()
    for (const e of timetable.entries ?? []) {
      for (const id of [e.teacher_id, e.assistant_teacher_id]) {
        if (id == null) continue
        if (!periods.has(id)) periods.set(id, new Set())
        periods.get(id).add(e.period_id)
      }
    }
    return new Map([...periods].map(([id, set]) => [id, set.size]))
  }, [timetable])
}

// This teacher's committed periods/week across every section in the
// school, from the plan (SubjectRequirement.preferred_teacher_id) — not
// the generated timetable. That's a deliberate scope choice: this is
// meant to warn about overload *while an admin is still assigning
// teachers*, before anyone has generated anything, so it can only count
// what's been explicitly pinned. A subject left on "Any (let solver
// choose)" doesn't show up here for anyone, since nothing — including
// the app — knows yet who'll actually teach it; the true final total
// (including solver-assigned subjects) only exists once a timetable has
// been generated, which is a separate, later feature.
//
// Includes elective block options pinned to this teacher: an option runs in
// every one of its block's periods, so it is that many periods of their week.
function teacherWorkload(teacherId, allRequirements, subjects, classGroups, electiveBlocks = []) {
  const optionRows = electiveBlocks.flatMap((b) =>
    b.options
      .filter((o) => o.preferred_teacher_id === teacherId)
      .map((o) => ({
        id: `block-option-${o.id}`,
        class_group_id: b.class_group_id,
        subject_id: o.subject_id,
        periods_per_week: b.periods_per_week,
        blockName: b.name,
      })),
  )
  const rows = [...allRequirements.filter((r) => r.preferred_teacher_id === teacherId), ...optionRows]
    .map((r) => ({
      ...r,
      subjectName: subjects.find((s) => s.id === r.subject_id)?.name ?? 'Unknown subject',
      classGroup: classGroups.find((cg) => cg.id === r.class_group_id),
    }))
  const total = rows.reduce((sum, r) => sum + r.periods_per_week, 0)
  return { rows, total }
}

export default function TeachersSection({ schoolId, teachers, subjects, classGroups, allRequirements, onTeachersChanged, readOnly }) {
  const { data: electiveBlocks = [] } = useElectiveBlocks(schoolId)
  const realLoad = useRealLoad(schoolId)
  const [search, setSearch] = useState('')
  const [sort, setSortState] = useState(() => loadChoice(SORT_KEY, 'name'))
  const setSort = (value) => {
    setSortState(value)
    saveChoice(SORT_KEY, value)
  }
  const [error, setError] = useState(null)
  const [showImport, setShowImport] = useState(true)
  const [addTeacherOpen, setAddTeacherOpen] = useState(false)
  const [openDropdownId, setOpenDropdownId] = useState(null)
  const [openGradeDropdownId, setOpenGradeDropdownId] = useState(null)
  // Which teacher's name/email/weekly-limit is currently being edited
  // (teacher id, or null) — everything else about a teacher (subjects,
  // grades, assistant eligibility) is already directly editable inline;
  // this covers the basic fields that weren't yet.
  const [editingTeacherId, setEditingTeacherId] = useState(null)

  const allGrades = distinctGrades(classGroups)

  // What the card shows and what "periods/week" sorts by.
  const loadOf = (teacher) =>
    realLoad
      ? realLoad.get(teacher.id) ?? 0
      : teacherWorkload(teacher.id, allRequirements, subjects, classGroups, electiveBlocks).total

  const subjectName = (id) => subjects.find((x) => x.id === id)?.name ?? ''
  // Searched by name, subjects and grades - typing "Hindi" finds every Hindi
  // teacher - then ordered by the chosen sort, alphabetically within ties.
  const shownTeachers = teachers
    .filter((t) =>
      matchesSearch(
        [t.name, ...(t.qualified_subject_ids || []).map(subjectName), ...(t.qualified_grades || [])].join(' '),
        search,
      ),
    )
    .sort((a, b) => {
      const name = compareNames(a.name, b.name)
      switch (sort) {
        case 'name-desc':
          return -name
        case 'load-desc':
          return loadOf(b) - loadOf(a) || name
        case 'load-asc':
          return loadOf(a) - loadOf(b) || name
        case 'subjects':
          return (b.qualified_subject_ids?.length ?? 0) - (a.qualified_subject_ids?.length ?? 0) || name
        case 'grades': {
          // By the lowest grade taught; "all grades" (no restriction) last.
          const low = (t) => [...(t.qualified_grades || [])].sort(compareNames)[0]
          const la = low(a)
          const lb = low(b)
          if (la == null || lb == null) return (la == null) - (lb == null) || name
          return compareNames(la, lb) || name
        }
        default:
          return name
      }
    })

  async function handleAssignSubject(teacher, subjectId) {
    try {
      await onTeachersChanged.update(teacher.id, {
        qualified_subject_ids: [...teacher.qualified_subject_ids, subjectId],
      })
      setOpenDropdownId(null)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUnassignSubject(teacher, subjectId) {
    try {
      await onTeachersChanged.update(teacher.id, {
        qualified_subject_ids: teacher.qualified_subject_ids.filter((id) => id !== subjectId),
      })
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleAssignGrade(teacher, grade) {
    try {
      await onTeachersChanged.update(teacher.id, {
        qualified_grades: [...(teacher.qualified_grades || []), grade],
      })
      setOpenGradeDropdownId(null)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUnassignGrade(teacher, grade) {
    try {
      await onTeachersChanged.update(teacher.id, {
        qualified_grades: (teacher.qualified_grades || []).filter((g) => g !== grade),
      })
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleToggleAssistantEligible(teacher) {
    try {
      await onTeachersChanged.update(teacher.id, {
        is_assistant_eligible: !teacher.is_assistant_eligible,
      })
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteTeacher(teacher) {
    const ok = await confirmDialog({
      title: `Remove ${teacher.name}?`,
      message: "This also removes them from every subject and section they're assigned to.",
      confirmLabel: 'Remove',
      danger: true,
    })
    if (!ok) return
    try {
      await onTeachersChanged.delete(teacher.id)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h4 className="text-base font-medium">Teachers</h4>
          <p className="mt-1 text-sm text-slate-500">Who teaches, and which subjects they cover.</p>
        </div>
        {!readOnly && (
          <button
            onClick={() => setAddTeacherOpen(true)}
            className="w-fit rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
          >
            + Add teacher
          </button>
        )}
      </div>

      <AnimatePresence>
        {addTeacherOpen && (
          <AddTeacherModal
            schoolId={schoolId}
            subjects={subjects}
            allGrades={allGrades}
            onClose={() => setAddTeacherOpen(false)}
            onAdded={async () => {
              setAddTeacherOpen(false)
              await onTeachersChanged.reload()
            }}
          />
        )}
      </AnimatePresence>

      {!readOnly && (
        <div className="rounded-lg border border-neutral-200 bg-neutral-100/40 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h5 className="text-sm font-semibold text-neutral-900">Import teachers</h5>
              <p className="mt-0.5 text-xs text-neutral-700/80">
                Upload a spreadsheet instead of adding teachers one at a time. Add subjects first,
                 since teacher rows are matched against subject names that already exist.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowImport((v) => !v)}
              className="flex-none text-xs font-medium text-neutral-700 hover:underline"
            >
              {showImport ? 'Hide' : 'Show'}
            </button>
          </div>
          {showImport && (
            <div className="mt-3">
              <BulkImportPanel schoolId={schoolId} resource="teachers" onImported={onTeachersChanged.reload} />
            </div>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      {teachers.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            aria-label="Search teachers"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, subject or grade"
            className="w-64 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            Sort by
            <select
              aria-label="Sort teachers"
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-xs text-slate-700"
            >
              {SORTS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {search.trim() && (
            <span className="text-xs text-slate-400">
              {shownTeachers.length} of {teachers.length}
            </span>
          )}
        </div>
      )}

      <div className="flex flex-col divide-y divide-slate-100 rounded-md border border-slate-200">
        {shownTeachers.map((teacher) => {
          const qualified = sortByName(subjects.filter((s) => teacher.qualified_subject_ids.includes(s.id)))
          // Excludes subjects still `_pending` (optimistically shown right
          // after "+ Add subject" but not yet confirmed by the server) —
          // picking one here before it has a real id would send that
          // temporary id to the backend instead of a valid subject id.
          const available = subjects.filter((s) => !s._pending && !teacher.qualified_subject_ids.includes(s.id))
          const qualifiedGrades = [...(teacher.qualified_grades || [])].sort(compareNames)
          const availableGrades = allGrades.filter((g) => !qualifiedGrades.includes(g))
          const workload = teacherWorkload(teacher.id, allRequirements, subjects, classGroups, electiveBlocks)
          // The real load once a timetable exists; until then, what's pinned.
          const load = loadOf(teacher)
          const overLimit = teacher.max_periods_per_week != null && load > teacher.max_periods_per_week
          const nearLimit =
            !overLimit && teacher.max_periods_per_week != null && load >= teacher.max_periods_per_week * 0.9
          if (editingTeacherId === teacher.id) {
            return (
              <div key={teacher.id} className="p-3">
                <TeacherEditForm
                  teacher={teacher}
                  onCancel={() => setEditingTeacherId(null)}
                  onSave={async (data) => {
                    try {
                      await onTeachersChanged.update(teacher.id, data)
                      setEditingTeacherId(null)
                    } catch (err) {
                      setError(err.message)
                    }
                  }}
                />
              </div>
            )
          }
          return (
            <div key={teacher.id} className="group flex flex-col gap-2 p-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="w-40 flex-none">
                <div className="flex items-center gap-1">
                  <span className="font-medium">{teacher.name}</span>
                  {!readOnly && (
                    <button
                      onClick={() => setEditingTeacherId(teacher.id)}
                      title={`Edit ${teacher.name}`}
                      aria-label={`Edit ${teacher.name}`}
                      className="opacity-0 text-slate-300 hover:text-neutral-900 group-hover:opacity-100 focus:opacity-100"
                    >
                      ✎
                    </button>
                  )}
                </div>
                {classGroups.some((cg) => cg.class_teacher_id === teacher.id) && (
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {classGroups
                      .filter((cg) => cg.class_teacher_id === teacher.id)
                      .map((cg) => (
                        <span key={cg.id} className="rounded-full bg-violet-50 px-2 py-0.5 text-xs text-violet-800">
                          Class teacher · {cg.grade ? `${cg.grade} ${cg.name}` : cg.name}
                        </span>
                      ))}
                  </div>
                )}
                <div
                  className={`text-xs font-medium ${
                    overLimit ? 'text-red-600' : nearLimit ? 'text-amber-600' : 'text-slate-400'
                  }`}
                  title={
                    teacher.max_periods_per_week
                      ? overLimit
                        ? `Over their ${teacher.max_periods_per_week}/week limit`
                        : `Limit: ${teacher.max_periods_per_week}/week`
                      : 'No weekly limit set for this teacher'
                  }
                >
                  {load} {load === 1 ? 'period' : 'periods'}/week
                  {teacher.max_periods_per_week ? ` of ${teacher.max_periods_per_week}` : ''}
                </div>
                <div className="text-[11px] text-slate-400">
                  {realLoad
                    ? workload.total > 0
                      ? `in the timetable · ${workload.total} pinned on plans`
                      : 'in the timetable'
                    : 'pinned on plans (generate for the real load)'}
                </div>
              </div>
              <div className="relative flex flex-1 flex-wrap items-center gap-1.5">
                <AnimatePresence initial={false}>
                  {qualified.map((s) => (
                    <motion.span
                      key={s.id}
                      layout
                      initial={{ opacity: 0, scale: 0.85 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.85 }}
                      transition={{ duration: 0.15 }}
                      className="inline-flex items-center gap-1.5 rounded-full bg-neutral-900 px-2.5 py-1 text-xs text-white"
                    >
                      {s.name}
                      {!readOnly && (
                        <button
                          onClick={() => handleUnassignSubject(teacher, s.id)}
                          aria-label={`Remove ${s.name} from ${teacher.name}`}
                          className="opacity-70 hover:opacity-100"
                        >
                          ✕
                        </button>
                      )}
                    </motion.span>
                  ))}
                </AnimatePresence>
                {!readOnly && (
                  <motion.button
                    whileHover={{ scale: 1.04 }}
                    whileTap={{ scale: 0.96 }}
                    onClick={() => setOpenDropdownId(openDropdownId === teacher.id ? null : teacher.id)}
                    className="rounded-full border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  >
                    + Add
                  </motion.button>
                )}
                <AnimatePresence>
                  {openDropdownId === teacher.id && (
                    <PickerPopover
                      ariaLabel={`Add a subject to ${teacher.name}`}
                      items={available}
                      getLabel={(subject) => subject.name}
                      emptyText={subjects.length === 0 ? 'No subjects yet' : 'Already teaches everything'}
                      onPick={(subject) => handleAssignSubject(teacher, subject.id)}
                      className="absolute left-0 top-7 z-10"
                    />
                  )}
                </AnimatePresence>
              </div>
              {!readOnly && (
                <button
                  onClick={() => handleDeleteTeacher(teacher)}
                  className="flex-none text-slate-300 hover:text-red-600"
                  title={`Remove ${teacher.name}`}
                  aria-label={`Remove ${teacher.name}`}
                >
                  ✕
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-1.5 pl-0 sm:pl-[172px]">
              <span className="mr-1 flex-none text-xs text-slate-400">Grades:</span>
              {qualifiedGrades.length === 0 && (
                <span className="text-xs text-slate-400">All grades</span>
              )}
              <AnimatePresence initial={false}>
                {qualifiedGrades.map((g) => (
                  <motion.span
                    key={g}
                    layout
                    initial={{ opacity: 0, scale: 0.85 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.85 }}
                    transition={{ duration: 0.15 }}
                    className="inline-flex items-center gap-1.5 rounded-full bg-slate-700 px-2.5 py-1 text-xs text-white"
                  >
                    {g}
                    {!readOnly && (
                      <button
                        onClick={() => handleUnassignGrade(teacher, g)}
                        aria-label={`Remove ${g} from ${teacher.name}`}
                        className="opacity-70 hover:opacity-100"
                      >
                        ✕
                      </button>
                    )}
                  </motion.span>
                ))}
              </AnimatePresence>
              {!readOnly && allGrades.length > 0 && (
                <div className="relative">
                  <motion.button
                    whileHover={{ scale: 1.04 }}
                    whileTap={{ scale: 0.96 }}
                    onClick={() => setOpenGradeDropdownId(openGradeDropdownId === teacher.id ? null : teacher.id)}
                    className="rounded-full border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  >
                    {qualifiedGrades.length === 0 ? '+ Restrict to specific grades' : '+ Add'}
                  </motion.button>
                  <AnimatePresence>
                    {openGradeDropdownId === teacher.id && (
                      <PickerPopover
                        ariaLabel={`Add a grade to ${teacher.name}`}
                        items={availableGrades}
                        getLabel={(grade) => grade}
                        emptyText="Already covers every grade"
                        onPick={(grade) => handleAssignGrade(teacher, grade)}
                        className="absolute left-0 top-7 z-10"
                      />
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>

            <div className="pl-0 sm:pl-[172px]">
              <label className="flex w-fit cursor-pointer items-center gap-1.5 text-xs text-slate-500">
                <input
                  type="checkbox"
                  checked={teacher.is_assistant_eligible}
                  disabled={readOnly}
                  onChange={() => handleToggleAssistantEligible(teacher)}
                  className="h-3.5 w-3.5 rounded border-slate-300"
                />
                Eligible as an assistant teacher
              </label>
            </div>

            {workload.rows.length > 0 && (
              <div className="pl-0 sm:pl-[172px]">
                <table className="w-fit min-w-[280px] border-collapse text-xs">
                  <thead>
                    <tr className="text-slate-400">
                      <th className="border-b border-slate-200 py-1 pr-4 text-left font-medium">Subject</th>
                      <th className="border-b border-slate-200 py-1 pr-4 text-left font-medium">Class</th>
                      <th className="border-b border-slate-200 py-1 text-right font-medium">Periods/week</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workload.rows.map((r) => (
                      <tr key={r.id}>
                        <td className="border-b border-slate-100 py-1 pr-4 text-slate-700">
                          {r.subjectName}
                          {r.blockName && <span className="ml-1 text-slate-400">({r.blockName})</span>}
                        </td>
                        <td className="border-b border-slate-100 py-1 pr-4 text-slate-500">
                          {r.classGroup ? `${r.classGroup.grade ? `${r.classGroup.grade} · ` : ''}Sec ${r.classGroup.name}` : 'Unknown section'}
                        </td>
                        <td className="border-b border-slate-100 py-1 text-right font-medium text-slate-700">
                          {r.periods_per_week}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td colSpan={2} className="pt-1 text-right text-slate-400">Total</td>
                      <td className="pt-1 text-right font-semibold text-slate-700">{workload.total}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            </div>
          )
        })}
        {teachers.length === 0 && (
          <p className="p-4 text-sm text-slate-500">No teachers yet. Add one above, or import a spreadsheet.</p>
        )}
        {teachers.length > 0 && shownTeachers.length === 0 && (
          <p className="p-4 text-sm text-slate-500">No teachers match "{search.trim()}".</p>
        )}
      </div>
    </div>
  )
}

/**
 * Inline edit for a teacher's basic fields — name, email, and weekly
 * period limit. Everything else about a teacher (subjects, grades,
 * assistant eligibility) is already editable directly on their row via
 * chips/checkboxes; these three fields weren't, and "the teacher's name
 * is wrong" or "we need to raise/lower their weekly limit" are both real,
 * ordinary corrections an admin needs a way to make after creation.
 */
function TeacherEditForm({ teacher, onSave, onCancel }) {
  const [name, setName] = useState(teacher.name)
  const [email, setEmail] = useState(teacher.email || '')
  const [maxPeriods, setMaxPeriods] = useState(
    teacher.max_periods_per_week != null ? String(teacher.max_periods_per_week) : ''
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function handleSave() {
    if (!name.trim() || saving) return
    setSaving(true)
    setError(null)
    try {
      await onSave({
        name: name.trim(),
        email: email.trim() || null,
        max_periods_per_week: maxPeriods.trim() ? Number(maxPeriods) : null,
      })
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-md bg-neutral-100/60 p-3 sm:flex-row sm:items-end sm:gap-3">
      <div className="flex flex-col gap-1">
        <label htmlFor={`edit-teacher-name-${teacher.id}`} className="text-xs font-medium text-slate-500">
          Name
        </label>
        <input
          id={`edit-teacher-name-${teacher.id}`}
          autoFocus
          value={name}
          disabled={saving}
          onChange={(e) => setName(e.target.value)}
          onFocus={(e) => e.target.select()}
          onKeyDown={(e) => e.key === 'Escape' && onCancel()}
          className="w-40 rounded border border-slate-300 px-2 py-1 text-sm focus:border-neutral-900 focus:outline-none disabled:opacity-60"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`edit-teacher-email-${teacher.id}`} className="text-xs font-medium text-slate-500">
          Email (optional)
        </label>
        <input
          id={`edit-teacher-email-${teacher.id}`}
          type="email"
          value={email}
          disabled={saving}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && onCancel()}
          className="w-48 rounded border border-slate-300 px-2 py-1 text-sm focus:border-neutral-900 focus:outline-none disabled:opacity-60"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`edit-teacher-max-${teacher.id}`} className="text-xs font-medium text-slate-500">
          Max periods/week (optional)
        </label>
        <input
          id={`edit-teacher-max-${teacher.id}`}
          type="number"
          min="0"
          value={maxPeriods}
          disabled={saving}
          onChange={(e) => setMaxPeriods(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSave()
            if (e.key === 'Escape') onCancel()
          }}
          className="w-28 rounded border border-slate-300 px-2 py-1 text-sm focus:border-neutral-900 focus:outline-none disabled:opacity-60"
        />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={!name.trim() || saving}
          className="rounded-md bg-neutral-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

/**
 * Modal for adding a teacher with their subjects in one step, instead of
 * creating a name-only teacher and then having to find them in every
 * relevant subject's "+ Add" dropdown one at a time. A teacher can teach
 * more than one subject (e.g. a Math teacher who also covers Physics), so
 * this is a multi-select checkbox list, not a single dropdown — mirrors
 * how `qualified_subject_ids` is actually modeled (a list) rather than
 * implying one teacher = one subject.
 */
function AddTeacherModal({ schoolId, subjects, allGrades, onClose, onAdded }) {
  const [name, setName] = useState('')
  const [selectedSubjectIds, setSelectedSubjectIds] = useState([])
  // Empty = no restriction (teaches every grade) — same default as
  // Teacher.qualified_grades server-side, so leaving this untouched here
  // behaves exactly like every teacher did before this field existed.
  const [selectedGrades, setSelectedGrades] = useState([])
  const [isAssistantEligible, setIsAssistantEligible] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  function toggleSubject(id) {
    setSelectedSubjectIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  function toggleGrade(grade) {
    setSelectedGrades((prev) =>
      prev.includes(grade) ? prev.filter((g) => g !== grade) : [...prev, grade]
    )
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await api.createTeacher({
        school_id: schoolId,
        name: name.trim(),
        qualified_subject_ids: selectedSubjectIds,
        qualified_grades: selectedGrades,
        is_assistant_eligible: isAssistantEligible,
      })
      await onAdded()
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 6 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 6 }}
        transition={{ duration: 0.15, ease: 'easeOut' }}
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl"
      >
        <h3 className="text-base font-semibold">Add teacher</h3>
        <form onSubmit={handleSubmit} className="mt-3 flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="new-teacher-name" className="text-xs font-medium text-slate-500">
              Name
            </label>
            <input
              id="new-teacher-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Teacher name"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-500">
              Subjects they teach (optional; a teacher can teach more than one)
            </span>
            {subjects.filter((s) => !s._pending).length === 0 ? (
              <p className="text-xs text-slate-400">
                No subjects yet. Add subjects first, or add this teacher now and assign
                subjects afterward from this list.
              </p>
            ) : (
              <div className="max-h-48 overflow-y-auto rounded-md border border-slate-200 p-2">
                {sortByName(subjects.filter((s) => !s._pending)).map((s) => (
                  <label
                    key={s.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selectedSubjectIds.includes(s.id)}
                      onChange={() => toggleSubject(s.id)}
                    />
                    {s.name}
                  </label>
                ))}
              </div>
            )}
          </div>

          {allGrades.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-500">
                Grades they teach (optional; leave all unchecked to teach every grade)
              </span>
              <div className="max-h-32 overflow-y-auto rounded-md border border-slate-200 p-2">
                {allGrades.map((g) => (
                  <label
                    key={g}
                    className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selectedGrades.includes(g)}
                      onChange={() => toggleGrade(g)}
                    />
                    {g}
                  </label>
                ))}
              </div>
            </div>
          )}

          <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-500">
            <input
              type="checkbox"
              checked={isAssistantEligible}
              onChange={(e) => setIsAssistantEligible(e.target.checked)}
            />
            Eligible as an assistant teacher
          </label>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="mt-1 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              disabled={!name.trim() || submitting}
              className="rounded-md bg-neutral-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {submitting ? 'Adding…' : 'Add teacher'}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  )
}

/**
 * The "+ Add" list for a teacher's subjects or grades: alphabetical, with a
 * search box that narrows it as you type and Enter adding the best match.
 */
function PickerPopover({ ariaLabel, items, getLabel, emptyText, onPick, className = '' }) {
  const [query, setQuery] = useState('')
  const shown = rankMatches(items, query, getLabel)
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: -4 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96, y: -4 }}
      transition={{ duration: 0.12, ease: 'easeOut' }}
      className={`w-52 rounded-md border border-slate-200 bg-white p-1 shadow-md ${className}`}
    >
      {items.length > 0 && (
        <input
          autoFocus
          aria-label={ariaLabel}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && shown[0] !== undefined) {
              e.preventDefault()
              onPick(shown[0])
            }
          }}
          placeholder="Type to search"
          className="mb-1 w-full rounded border border-slate-200 px-2 py-1 text-sm focus:border-neutral-900 focus:outline-none"
        />
      )}
      <div className="max-h-52 overflow-y-auto">
        {items.length === 0 && <p className="px-2 py-1.5 text-xs text-slate-400">{emptyText}</p>}
        {items.length > 0 && shown.length === 0 && (
          <p className="px-2 py-1.5 text-xs text-slate-400">No matches</p>
        )}
        {shown.map((item) => (
          <div
            key={getLabel(item)}
            role="option"
            aria-selected={false}
            onClick={() => onPick(item)}
            className="cursor-pointer rounded px-2 py-1.5 text-sm hover:bg-slate-50"
          >
            {getLabel(item)}
          </div>
        ))}
      </div>
    </motion.div>
  )
}
