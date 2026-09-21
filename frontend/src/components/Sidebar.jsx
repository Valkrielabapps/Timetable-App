import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import BulkAddClassGroups from './BulkAddClassGroups'

// Numeric-aware comparison so "Grade 2" sorts before "Grade 10" — a plain
// string sort would put "Grade 10" right after "Grade 1", ahead of every
// other single-digit grade. Falls back to a plain locale compare for
// non-numeric labels (e.g. "Nursery", "LKG") where there's no number to
// anchor on.
function naturalGradeCompare(a, b) {
  const numA = a.match(/\d+/)
  const numB = b.match(/\d+/)
  if (numA && numB) {
    const diff = Number(numA[0]) - Number(numB[0])
    if (diff !== 0) return diff
  }
  return a.localeCompare(b)
}

// Sorts grade keys by the school's explicit `gradeOrder` (admin-set via
// the Reorder mode below) when one exists, falling back to the natural
// sort above for any grade not yet in that list — a school that's never
// touched reordering gets a sensibly-ordered sidebar for free, and a
// brand-new grade added after the last reorder still shows up (at the
// end) instead of silently disappearing from the list. "Ungrouped"
// (sections with no grade set) always sorts last — it's not a real grade,
// just where sections with none land.
function sortGradeKeys(keys, gradeOrder) {
  const order = gradeOrder && gradeOrder.length > 0 ? gradeOrder : null
  return [...keys].sort((a, b) => {
    if (a === 'Ungrouped' || b === 'Ungrouped') {
      if (a === b) return 0
      return a === 'Ungrouped' ? 1 : -1
    }
    if (order) {
      const ia = order.indexOf(a)
      const ib = order.indexOf(b)
      const ra = ia === -1 ? order.length : ia
      const rb = ib === -1 ? order.length : ib
      if (ra !== rb) return ra - rb
    }
    return naturalGradeCompare(a, b)
  })
}

/**
 * Left nav: school branding + switcher, then a Grade > Section tree built
 * from class groups grouped by their `grade` field. Ungrouped class groups
 * (grade is null) show under an "Ungrouped" heading so nothing silently
 * disappears from the tree.
 *
 * Motion notes (kept deliberately restrained — this is admin software, not
 * a marketing page): the selected section's highlight is a single shared
 * `motion.div` (`layoutId="sidebar-active-pill"`) that Framer Motion
 * animates between positions instead of the highlight just teleporting on
 * every click — same trick used by most polished dashboard sidebars.
 * Grade groups expand/collapse with a real height animation instead of
 * instantly showing/hiding. Hover/tap use tiny (2px/0.99 scale) offsets,
 * not the bouncier spring/scale treatment used on the landing page —
 * this needs to feel calm and precise, not playful.
 */
export default function Sidebar({
  schoolName,
  institutionType,
  onUpdateInstitutionType,
  schools,
  selectedSchoolId,
  onSelectSchool,
  onAddSchool,
  classGroups,
  selectedClassGroupId,
  onSelectClassGroup,
  onAddClassGroup,
  onAddClassGroups,
  onDeleteClassGroup,
  onUpdateClassGroup,
  onRenameGrade,
  gradeOrder,
  onReorderGrades,
  onGoToDataEntry,
  activeDataEntrySubView,
  readOnly = false,
}) {
  const [expanded, setExpanded] = useState({})
  const [addingGrade, setAddingGrade] = useState(false)
  const [addMode, setAddMode] = useState('single') // 'single' | 'range'
  const [newGrade, setNewGrade] = useState('')
  const [newSection, setNewSection] = useState('')
  const [submittingSection, setSubmittingSection] = useState(false)
  // Which grade heading is currently being renamed (grade key, or null).
  const [editingGrade, setEditingGrade] = useState(null)
  // Swaps the rename pencil for up/down arrows on every grade heading —
  // a toggle rather than always-visible arrows, since most admins only
  // need this once (right after adding grades out of order) and constant
  // arrows next to every heading would be visual noise the rest of the time.
  const [reorderMode, setReorderMode] = useState(false)
  // Which section is currently being edited (class group id, or null) —
  // edit mode swaps the row for a small grade+name form instead of a
  // single text field, since fixing a typo and moving a section to a
  // different grade are the same "correct this section" action to an
  // admin, not two separate features.
  const [editingSectionId, setEditingSectionId] = useState(null)
  // Whether the school/college pill next to the school switcher has
  // swapped for its own tiny dropdown — see the institution-type block
  // near the top of the render below.
  const [editingType, setEditingType] = useState(false)
  // Optimistic override for gradeOrder, used only while a reorder is
  // in flight. Without this, every up/down click waited on a full
  // round trip to the server (through Railway, then Supabase) before
  // the arrows visually moved anything — on a slow connection that
  // looked like nothing happened, and clicking again before the first
  // request resolved computed the next swap from the same stale
  // pre-move order both times, so rapid clicks could silently no-op or
  // even race each other's saves. Set immediately on click; cleared
  // once the confirmed `gradeOrder` prop catches up (see the effect
  // below), so the prop is the source of truth again as soon as it can be.
  const [localGradeOrder, setLocalGradeOrder] = useState(null)

  useEffect(() => {
    setLocalGradeOrder(null)
  }, [gradeOrder])

  const effectiveGradeOrder = localGradeOrder ?? gradeOrder

  const grades = useMemo(() => {
    const map = new Map()
    for (const cg of classGroups) {
      const key = cg.grade || 'Ungrouped'
      if (!map.has(key)) map.set(key, [])
      map.get(key).push(cg)
    }
    const sortedKeys = sortGradeKeys([...map.keys()], effectiveGradeOrder)
    return sortedKeys.map((key) => [key, map.get(key)])
  }, [classGroups, effectiveGradeOrder])

  // "Ungrouped" is pinned last by sortGradeKeys and isn't a real grade, so
  // it's excluded here — it can't be moved, and there's no reason to
  // persist it in the school's saved gradeOrder.
  const orderableGradeKeys = grades.map(([g]) => g).filter((g) => g !== 'Ungrouped')

  function moveGrade(grade, direction) {
    const idx = orderableGradeKeys.indexOf(grade)
    const swapIdx = idx + direction
    if (idx === -1 || swapIdx < 0 || swapIdx >= orderableGradeKeys.length) return
    const next = [...orderableGradeKeys]
    ;[next[idx], next[swapIdx]] = [next[swapIdx], next[idx]]
    setLocalGradeOrder(next) // instant, so the next click (if any) builds on this, not stale state
    onReorderGrades(next)
  }

  function resetGradeOrder() {
    setLocalGradeOrder([])
    onReorderGrades([])
  }

  function toggle(grade) {
    setExpanded((prev) => ({ ...prev, [grade]: !prev[grade] }))
  }

  async function handleAddSubmit(e) {
    e.preventDefault()
    if (!newGrade.trim() || !newSection.trim() || submittingSection) return
    setSubmittingSection(true)
    try {
      await onAddClassGroup(newGrade.trim(), newSection.trim())
      setNewGrade('')
      setNewSection('')
      setAddingGrade(false)
    } finally {
      setSubmittingSection(false)
    }
  }

  return (
    <aside className="flex w-68 flex-none flex-col gap-4 border-r border-slate-200 bg-white p-3.5" style={{ width: 272 }}>
      <div className="flex items-center gap-2.5 px-1">
        <div className="flex h-8 w-8 flex-none items-center justify-center rounded-md border border-neutral-900 text-sm font-semibold text-slate-900">
          {schoolName?.[0]?.toUpperCase() || 'S'}
        </div>
        <div className="min-w-0">
          {schools.length > 1 ? (
            <select
              value={selectedSchoolId ?? ''}
              onChange={(e) => onSelectSchool(Number(e.target.value))}
              className="w-full truncate bg-transparent text-sm font-semibold focus:outline-none"
            >
              {schools.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          ) : (
            <div className="truncate text-sm font-semibold leading-tight">{schoolName}</div>
          )}
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <span>Admin</span>
            <span className="text-slate-300">·</span>
            {editingType ? (
              <select
                autoFocus
                value={institutionType || 'school'}
                onChange={(e) => {
                  onUpdateInstitutionType?.(e.target.value)
                  setEditingType(false)
                }}
                onBlur={() => setEditingType(false)}
                className="rounded border border-slate-300 bg-white px-1 py-0.5 text-xs focus:outline-none"
              >
                <option value="school">School</option>
                <option value="college">College</option>
              </select>
            ) : (
              !readOnly && onUpdateInstitutionType ? (
                <button
                  onClick={() => setEditingType(true)}
                  className="underline decoration-dotted underline-offset-2 hover:text-slate-700"
                  title="Change whether this is set up as a school or a college"
                >
                  {institutionType === 'college' ? 'College' : 'School'}
                </button>
              ) : (
                <span>{institutionType === 'college' ? 'College' : 'School'}</span>
              )
            )}
          </div>
        </div>
      </div>

      <div className="h-px bg-slate-200" />

      {onGoToDataEntry && (
        <div className="flex flex-col gap-0.5">
          <button
            onClick={() => onGoToDataEntry('subjects')}
            className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm font-medium ${
              activeDataEntrySubView === 'subjects' ? 'bg-neutral-100 text-neutral-900' : 'text-slate-600 hover:bg-slate-50'
            }`}
            title="What the school teaches — not tied to any one section"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-none opacity-70">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
            Subjects
          </button>
          <button
            onClick={() => onGoToDataEntry('teachers')}
            className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm font-medium ${
              activeDataEntrySubView === 'teachers' ? 'bg-neutral-100 text-neutral-900' : 'text-slate-600 hover:bg-slate-50'
            }`}
            title="Who teaches, and which subjects they cover — not tied to any one section"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-none opacity-70">
              <circle cx="9" cy="7" r="3.5" />
              <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
              <path d="M16.5 4.2c1.4.4 2.5 1.7 2.5 3.3s-1.1 2.9-2.5 3.3" />
              <path d="M19 14.3c1.7.6 3 2.1 3 3.7" />
            </svg>
            Teachers
          </button>
          <button
            onClick={() => onGoToDataEntry('setup')}
            className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm font-medium ${
              activeDataEntrySubView === 'setup' ? 'bg-neutral-100 text-neutral-900' : 'text-slate-600 hover:bg-slate-50'
            }`}
            title="Periods and rooms — the school's foundational, one-time setup"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-none opacity-70">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 13a7.6 7.6 0 0 0 0-2l2-1.5-2-3.5-2.4 1a7.7 7.7 0 0 0-1.7-1L15 3h-4l-.3 2.5a7.7 7.7 0 0 0-1.7 1l-2.4-1-2 3.5L6.6 11a7.6 7.6 0 0 0 0 2l-2 1.5 2 3.5 2.4-1a7.7 7.7 0 0 0 1.7 1L11 21h4l.3-2.5a7.7 7.7 0 0 0 1.7-1l2.4 1 2-3.5-2-1.5z" />
            </svg>
            Setup
          </button>
        </div>
      )}

      <div className="h-px bg-slate-200" />

      <div className="flex items-center justify-between px-1">
        <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
          Grades &amp; sections
        </span>
        <div className="flex items-center gap-2.5">
          {reorderMode && onReorderGrades && (
            <button
              onClick={resetGradeOrder}
              className="text-xs text-slate-400 hover:text-slate-700"
              title="Clear the custom order and go back to automatic sorting"
            >
              Auto-sort
            </button>
          )}
          {!readOnly && onReorderGrades && orderableGradeKeys.length > 1 && (
            <button
              onClick={() => setReorderMode((v) => !v)}
              className={`text-xs ${reorderMode ? 'font-medium text-neutral-900' : 'text-slate-400 hover:text-slate-700'}`}
              title="Reorder grades"
            >
              {reorderMode ? 'Done' : 'Reorder'}
            </button>
          )}
          {!readOnly && (
            <button
              onClick={() => setAddingGrade((v) => !v)}
              className="text-xs text-slate-400 hover:text-slate-700"
              title="Add grade / section"
            >
              + Add
            </button>
          )}
        </div>
      </div>

      <AnimatePresence initial={false}>
      {!readOnly && addingGrade && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="overflow-hidden"
        >
        <div className="flex flex-col gap-1.5 rounded-md bg-slate-50 p-2">
          <div className="flex gap-1 text-[11px]">
            <button
              type="button"
              onClick={() => setAddMode('single')}
              className={`rounded px-2 py-0.5 font-medium ${addMode === 'single' ? 'bg-neutral-900 text-white' : 'text-slate-500 hover:bg-slate-200'}`}
            >
              One
            </button>
            <button
              type="button"
              onClick={() => setAddMode('range')}
              className={`rounded px-2 py-0.5 font-medium ${addMode === 'range' ? 'bg-neutral-900 text-white' : 'text-slate-500 hover:bg-slate-200'}`}
            >
              Range
            </button>
          </div>

          {addMode === 'single' ? (
            <form onSubmit={handleAddSubmit} className="flex flex-col gap-1.5">
              <label htmlFor="sidebar-new-grade" className="sr-only">Grade / Year</label>
              <input
                id="sidebar-new-grade"
                value={newGrade}
                onChange={(e) => setNewGrade(e.target.value)}
                placeholder="Grade 8, or Semester 3"
                disabled={submittingSection}
                className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-60"
              />
              <label htmlFor="sidebar-new-section" className="sr-only">Section / Division</label>
              <input
                id="sidebar-new-section"
                value={newSection}
                onChange={(e) => setNewSection(e.target.value)}
                placeholder="A, or Div B"
                disabled={submittingSection}
                className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-60"
              />
              <button
                disabled={submittingSection}
                className="rounded bg-neutral-900 py-1 text-xs font-medium text-white disabled:opacity-60"
              >
                {submittingSection ? 'Adding…' : 'Add section'}
              </button>
            </form>
          ) : (
            <BulkAddClassGroups
              onAddClassGroups={onAddClassGroups}
              existing={classGroups}
              onDone={() => setAddingGrade(false)}
              institutionType={institutionType}
            />
          )}
        </div>
        </motion.div>
      )}
      </AnimatePresence>

      <div className="flex flex-1 flex-col gap-px overflow-y-auto">
        {grades.map(([grade, sections], i) => (
          <motion.div
            key={grade}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2, delay: Math.min(i, 8) * 0.03, ease: 'easeOut' }}
          >
            {editingGrade === grade ? (
              <GradeRenameForm
                initialValue={grade}
                onCancel={() => setEditingGrade(null)}
                onSave={async (newValue) => {
                  if (newValue.trim() && newValue.trim() !== grade) {
                    await onRenameGrade(grade, newValue.trim())
                  }
                  setEditingGrade(null)
                }}
              />
            ) : (
              <div
                onClick={() => toggle(grade)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    toggle(grade)
                  }
                }}
                className="group flex cursor-pointer items-center gap-1.5 rounded-md px-1.5 py-1.5 text-sm hover:bg-slate-50"
              >
                <span
                  className="inline-flex opacity-60 transition-transform"
                  style={{ transform: expanded[grade] ? 'rotate(90deg)' : 'rotate(0deg)' }}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </span>
                <span className="flex-1">{grade}</span>
                {reorderMode && grade !== 'Ungrouped' ? (
                  <span className="flex items-center gap-0.5">
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        moveGrade(grade, -1)
                      }}
                      disabled={orderableGradeKeys.indexOf(grade) === 0}
                      title={`Move "${grade}" up`}
                      aria-label={`Move ${grade} up`}
                      className="text-slate-400 hover:text-neutral-900 disabled:opacity-30 disabled:hover:text-slate-400"
                    >
                      ▲
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        moveGrade(grade, 1)
                      }}
                      disabled={orderableGradeKeys.indexOf(grade) === orderableGradeKeys.length - 1}
                      title={`Move "${grade}" down`}
                      aria-label={`Move ${grade} down`}
                      className="text-slate-400 hover:text-neutral-900 disabled:opacity-30 disabled:hover:text-slate-400"
                    >
                      ▼
                    </button>
                  </span>
                ) : (
                  !readOnly &&
                  onRenameGrade && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditingGrade(grade)
                      }}
                      title={`Rename "${grade}" (applies to all its sections)`}
                      aria-label={`Rename ${grade}`}
                      className="opacity-0 text-slate-300 hover:text-neutral-900 group-hover:opacity-100 focus:opacity-100"
                    >
                      ✎
                    </button>
                  )
                )}
              </div>
            )}
            <AnimatePresence initial={false}>
              {expanded[grade] !== false && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.16, ease: 'easeOut' }}
                  className="overflow-hidden"
                >
                <div className="mb-0.5 flex flex-col gap-px pl-6">
                  {sections.map((cg) => {
                    const selected = cg.id === selectedClassGroupId
                    if (editingSectionId === cg.id) {
                      return (
                        <SectionEditForm
                          key={cg.id}
                          classGroup={cg}
                          allGrades={grades.map(([g]) => g)}
                          onCancel={() => setEditingSectionId(null)}
                          onSave={async (data) => {
                            await onUpdateClassGroup(cg.id, data)
                            setEditingSectionId(null)
                          }}
                        />
                      )
                    }
                    return (
                      <motion.div
                        key={cg.id}
                        onClick={() => onSelectClassGroup(cg.id)}
                        role="button"
                        tabIndex={0}
                        aria-current={selected ? 'true' : undefined}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            onSelectClassGroup(cg.id)
                          }
                        }}
                        whileHover={selected ? undefined : { x: 2 }}
                        whileTap={{ scale: 0.99 }}
                        transition={{ duration: 0.12 }}
                        className="group relative flex cursor-pointer items-center justify-between rounded px-2.5 py-1.5 text-sm"
                      >
                        {selected && (
                          <motion.div
                            layoutId="sidebar-active-pill"
                            transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                            className="absolute inset-0 rounded border-l-2 border-neutral-900 bg-neutral-100"
                          />
                        )}
                        <span className={`relative z-10 ${selected ? 'font-medium text-neutral-900' : 'text-slate-600'}`}>
                          Section {cg.name}
                        </span>
                        {!readOnly && (
                          <span className="relative z-10 flex items-center gap-1.5 opacity-0 group-hover:opacity-100">
                            {onUpdateClassGroup && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setEditingSectionId(cg.id)
                                }}
                                title={`Edit Section ${cg.name}`}
                                aria-label={`Edit Section ${cg.name}`}
                                className="text-slate-300 hover:text-neutral-900 focus:opacity-100"
                              >
                                ✎
                              </button>
                            )}
                            {onDeleteClassGroup && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onDeleteClassGroup(cg)
                                }}
                                title={`Delete Section ${cg.name}`}
                                aria-label={`Delete Section ${cg.name}`}
                                className="text-slate-300 hover:text-red-600 focus:opacity-100"
                              >
                                ✕
                              </button>
                            )}
                          </span>
                        )}
                      </motion.div>
                    )
                  })}
                </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        ))}
        {grades.length === 0 && (
          <p className="px-1 py-2 text-xs text-slate-400">
            No grades yet — add one above to get started.
          </p>
        )}
      </div>

      <div className="h-px bg-slate-200" />
      <button
        onClick={onAddSchool}
        className="px-1 text-left text-xs text-slate-400 hover:text-slate-700"
      >
        + Add another school
      </button>
    </aside>
  )
}

/**
 * Inline rename for a grade heading. Since "grade" is just a shared
 * string across every section under it, saving renames all of them in
 * one action (see App.jsx's handleRenameGrade) rather than requiring an
 * admin to fix a shared typo section-by-section.
 */
function GradeRenameForm({ initialValue, onSave, onCancel }) {
  const [value, setValue] = useState(initialValue)
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    if (saving) return
    setSaving(true)
    try {
      await onSave(value)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center gap-1 px-1.5 py-1">
      <input
        autoFocus
        value={value}
        disabled={saving}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSave()
          if (e.key === 'Escape') onCancel()
        }}
        onFocus={(e) => e.target.select()}
        className="min-w-0 flex-1 rounded border border-neutral-400 px-1.5 py-0.5 text-sm focus:outline-none"
      />
      <button
        onClick={handleSave}
        disabled={saving}
        title="Save"
        className="text-slate-400 hover:text-neutral-900 disabled:opacity-50"
      >
        ✓
      </button>
      <button onClick={onCancel} disabled={saving} title="Cancel" className="text-slate-400 hover:text-slate-700 disabled:opacity-50">
        ✕
      </button>
    </div>
  )
}

/**
 * Inline edit for one section: name and grade together, since "fix a
 * typo" and "this section is actually in the wrong grade" are the same
 * "correct this section" action from an admin's point of view, not two
 * separate features. A datalist offers existing grades so moving a
 * section to an already-existing grade doesn't require retyping it
 * exactly (which would otherwise silently create a new, near-duplicate
 * grade heading).
 */
function SectionEditForm({ classGroup, allGrades, onSave, onCancel }) {
  const [grade, setGrade] = useState(classGroup.grade || '')
  const [name, setName] = useState(classGroup.name)
  const [saving, setSaving] = useState(false)
  const listId = `grade-options-${classGroup.id}`

  async function handleSave() {
    if (!name.trim() || saving) return
    setSaving(true)
    try {
      await onSave({ grade: grade.trim() || null, name: name.trim() })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-1 rounded bg-neutral-100/60 px-2 py-1.5">
      <label htmlFor={`edit-grade-${classGroup.id}`} className="sr-only">Grade</label>
      <input
        id={`edit-grade-${classGroup.id}`}
        list={listId}
        value={grade}
        disabled={saving}
        onChange={(e) => setGrade(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        placeholder="Grade"
        className="rounded border border-slate-300 px-1.5 py-0.5 text-xs focus:border-neutral-900 focus:outline-none"
      />
      <datalist id={listId}>
        {allGrades.map((g) => (
          <option key={g} value={g === 'Ungrouped' ? '' : g} />
        ))}
      </datalist>
      <label htmlFor={`edit-name-${classGroup.id}`} className="sr-only">Section name</label>
      <input
        id={`edit-name-${classGroup.id}`}
        autoFocus
        value={name}
        disabled={saving}
        onChange={(e) => setName(e.target.value)}
        onFocus={(e) => e.target.select()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSave()
          if (e.key === 'Escape') onCancel()
        }}
        placeholder="Section name"
        className="rounded border border-slate-300 px-1.5 py-0.5 text-xs focus:border-neutral-900 focus:outline-none"
      />
      <div className="flex justify-end gap-2 pt-0.5">
        <button onClick={onCancel} disabled={saving} className="text-xs text-slate-500 hover:text-slate-700 disabled:opacity-50">
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={saving || !name.trim()}
          className="text-xs font-medium text-neutral-900 hover:text-neutral-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}
