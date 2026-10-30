import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { pickVersions, versionLabel } from '../lib/versions'
import { api } from '../api'
import ScheduleGrid from './ScheduleGrid.jsx'
import {
  useApplyEntryUpdates,
  useElectiveBlocks,
  useFrozenStatus,
  useSetFrozen,
  useSubjectFreezeActions,
  useSubjectFreezes,
  useOptimisticSlotMove,
  useGenerateTimetable,
  useTimetable,
  useTimetables,
} from '../hooks/useSchoolData'
import { combinationsFor, keeps, MAX_COMBINATIONS } from '../studentCombinations'
import SubstitutionsTab from './SubstitutionsTab'
import SubjectFreezePanel from './SubjectFreezePanel'
import SearchableSelect from './SearchableSelect'
import { sortByName, sortSections } from '../sorting'
import { teacherLessons } from '../electiveSections'
import GenerationFailedDialog from './GenerationFailedDialog'
import { useEntitlements } from '../hooks/useEntitlements'

// Where the sidebar scrolls to. Derived from the id rather than passed around,
// so selecting a section needs no extra wiring between the two components.
const sectionAnchorId = (classGroupId) => `timetable-section-${classGroupId}`

// Failed generations whose reasons have already been shown and closed. Kept
// outside the component so switching tabs and back doesn't pop the same
// dialog up again; a new failed generation has a new id and does open it.
const seenFailures = new Set()

/**
 * Generates a timetable for the whole school (every section + every
 * teacher together, so there are no cross-section conflicts — see
 * backend/app/services/solver.py, which already reads every class group
 * in the school in one solve) and displays it as a day x period grid,
 * either for the currently selected section or for a chosen teacher
 * across all their sections.
 *
 * Generation runs as a background job on the backend (see
 * backend/app/routers/timetables.py) because a large school's solve can
 * take up to a minute — too long to hold an HTTP request open. So instead
 * of awaiting one blocking call, we kick the job off, get back a
 * "generating" row immediately, and poll GET /api/timetables/{id} on an
 * interval until status is no longer "generating".
 *
 * The Export links download the whole school's timetable as a single
 * file (every section + every teacher, one sheet/page each — see
 * backend/app/services/export.py), not just whatever's currently shown
 * on screen, since that's what an admin printing schedules actually
 * wants.
 *
 * Once a timetable is generated, individual slots can be hand-edited in
 * the "By Section" view: click a slot to lock/unlock it (locked = the next
 * regenerate leaves it exactly where it is — see lock-slot in
 * backend/app/routers/timetables.py, and the locked-entry handling in
 * backend/app/services/solver.py), or drag an unlocked slot to a different
 * period to move it by hand, swapping with whatever is there. The unit is
 * the slot, not the entry: an elective block (one entry per option) or a
 * split lab (one per batch) moves as a whole, because its parts always run
 * together. There's no
 * lock icon — locked/unlocked is shown as a light red/green tint on the
 * whole cell instead, so the state reads at a glance across the whole
 * grid. Moving goes through move-slot, which rejects the change with a
 * message if it would double-book a teacher or a room — that message is
 * what ends up in `error` and shown below the grid. Editing is section-view-only: the "By
 * Teacher" view mixes entries from several different classes, where "move
 * this" is ambiguous (though the red/green tint still shows there, as
 * information).
 *
 * The text box above the grid ("Or describe an edit...") is a
 * conversational alternative to dragging — POST
 * /api/timetables/{id}/edit-command (backend/app/services/
 * edit_command_parser.py) resolves plain English against this
 * timetable's actual entries and the school's actual periods (grounded
 * by id, not fuzzy-matched from text) and performs the SAME lock/move/
 * swap operation the drag-and-drop handlers below call. It can reference
 * any class group in the school by name, not just whichever one is
 * currently selected in the grid. There's no non-LLM fallback for this
 * one (unlike constraint parsing) — with no ANTHROPIC_API_KEY configured
 * it just returns an error telling the admin to drag instead, since
 * there's no fixed-pattern shortcut for "which of potentially hundreds of
 * entries did they mean" worth building.
 *
 * `page` toggles between this generated-schedule view and Substitutions
 * (SubstitutionsTab) — they used to be separate top-level tabs, but
 * Substitutions is really a sibling lens on the same generated timetable
 * (same data: entries, periods, teachers), not a distinct workflow, so it
 * lives here as a second view instead of adding to the top nav's tab
 * count.
 */
export default function TimetableTab({
  schoolId,
  classGroup,
  classGroups,
  teachers,
  // Only to name the subjects in each section's elective combinations.
  subjects = [],
  // periods/timetable/generating are App.jsx's own state now, not fetched
  // or held locally here — this component gets unmounted every time the
  // admin switches to another top-level tab
  // (`{tab === 'timetable' && (...)}` in App.jsx), so a just-generated
  // timetable kept only in this component's memory was destroyed on every
  // tab switch, making it look like it "disappeared" and prompting to
  // generate a new one. App.jsx fetches it once (as part of
  // loadSchoolData) and owns it from then on, including polling while a
  // generation is in progress — even while the admin is on a different
  // tab — so there's nothing left here that a remount can lose.
  periods,
  constraints = [],
  readOnly = false,
  onOpenConstraints,
}) {
  // Constraints saved on the Constraints tab that the solver doesn't
  // actually apply — most commonly the "scheduling_rule" catch-all for
  // free-text rules the parser couldn't map to a real constraint type
  // (see generate_school_timetable's docstring in
  // backend/app/services/solver.py), but any constraint's `enforced` flag
  // can come back false (e.g. an availability rule where no day was
  // recognized). Surfaced here, right before Generate, rather than only on
  // the Constraints tab itself — an admin who set up rules earlier and
  // comes straight to Timetable to generate would otherwise have no reason
  // to suspect some of them are silently no-ops.
  const unenforcedConstraints = constraints.filter((c) => !c.enforced)
  const [page, setPage] = useState('schedule') // 'schedule' | 'substitutions'
  const [view, setView] = useState('section') // 'section' | 'teacher'
  // The first teacher alphabetically, like the picker lists them.
  const [selectedTeacherId, setSelectedTeacherId] = useState(sortByName(teachers)[0]?.id ?? null)
  const [error, setError] = useState(null)
  // Where the dragged slot came from: { classGroupId, period }. The section
  // is kept so a drop into another section's grid can be refused rather than
  // quietly moving the slot inside its own.
  const [dragSource, setDragSource] = useState(null)
  // Which export format is currently downloading, if any — guards against
  // a double-click firing two downloads with no visual feedback either way.
  const [exporting, setExporting] = useState(null) // null | 'xlsx' | 'pdf'
  // Whether exports carry the Timetablz name. Leaving it off is a paid-plan
  // option; on Free, unticking opens the upgrade prompt instead.
  const [watermark, setWatermark] = useState(true)
  const { data: entitlements } = useEntitlements(schoolId)
  const cleanExportsAllowed = entitlements?.limits?.clean_exports !== false
  function toggleWatermark(next) {
    if (!next && !cleanExportsAllowed) {
      window.dispatchEvent(
        new CustomEvent('timetablz:plan-limit', {
          detail: {
            message:
              'Exporting without the Timetablz watermark is part of the Pro plan. Upgrade in Settings > Plan & billing.',
          },
        }),
      )
      return
    }
    setWatermark(next)
  }
  // Conversational editing (POST /api/timetables/{id}/edit-command) — a
  // plain-English alternative to drag-and-drop, e.g. "move Grade 8's Math
  // to period 2 on Wednesdays". Section-view-only, same reasoning as
  // drag-and-drop above. commandFeedback holds the last result (success
  // description or error message) so the admin gets confirmation of what
  // actually happened, since there's no visual drag to watch this time.
  const [commandText, setCommandText] = useState('')
  const [commandSubmitting, setCommandSubmitting] = useState(false)
  const [commandFeedback, setCommandFeedback] = useState(null) // { ok: bool, text: string } | null

  async function handleExport(format) {
    if (exporting) return
    setExporting(format)
    try {
      await api.downloadTimetableExport(timetable.id, format, { watermark })
    } catch (err) {
      setError(err.message)
    } finally {
      setExporting(null)
    }
  }

  useEffect(() => {
    // Re-syncs whenever the teacher list changes — not just when nothing
    // is selected. Without the "still valid" check, switching schools
    // could leave selectedTeacherId pointing at a teacher that doesn't
    // exist in the new school's list at all (a stale id from before),
    // silently rendering an empty "By Teacher" grid with no indication
    // why, until the admin happened to reselect manually.
    const stillValid = teachers.some((t) => t.id === selectedTeacherId)
    if (!stillValid) setSelectedTeacherId(sortByName(teachers)[0]?.id ?? null)
  }, [teachers, selectedTeacherId])

  // The latest timetable for this school, polled by useTimetable while the
  // solver is still working. Replaces App.jsx's setInterval + ref: the
  // interval is derived from the row's status, so it stops on its own and
  // resumes by itself after a reload mid-generation.
  const { data: timetableList = [] } = useTimetables(schoolId)
  // The school's current version, or a generation still running; a failure
  // after the current version is reported beside it, not instead of it.
  const { shownId, failure: failedVersion, current: currentVersion } = pickVersions(timetableList)
  const { data: timetable = null } = useTimetable(shownId)
  const { data: failureTimetable = null } = useTimetable(failedVersion?.id ?? null)

  const { generate, isGenerating: isSubmittingGenerate } = useGenerateTimetable(schoolId)
  const applyEntryUpdates = useApplyEntryUpdates(timetable?.id)
  const optimisticSlotMove = useOptimisticSlotMove(timetable?.id)
  const { data: electiveBlocks = [] } = useElectiveBlocks(schoolId)
  const subjectName = (id) => subjects.find((s) => s.id === id)?.name ?? '?'

  // Frozen sections keep their timetable through every later generation -
  // see backend/app/services/freezing.py. Keyed by the timetable on screen so
  // a new one re-checks whether each still matches what it was frozen with.
  const { data: frozenList = [] } = useFrozenStatus(schoolId, timetable?.id)
  const frozenById = new Map(frozenList.filter((f) => f.frozen).map((f) => [f.class_group_id, f]))
  const { setFrozen, isSaving: freezing } = useSetFrozen(schoolId, timetable?.id)

  // Frozen subjects keep one subject's lessons in place in the sections
  // chosen - see backend/app/services/subject_freezing.py.
  const { data: subjectFreezes = [] } = useSubjectFreezes(schoolId, timetable?.id)
  const subjectFreezing = useSubjectFreezeActions(schoolId, timetable?.id)
  const [freezeTab, setFreezeTab] = useState('sections') // 'sections' | 'subjects'

  async function handleFreeze(ids, frozen) {
    setError(null)
    try {
      await setFrozen(ids, frozen)
    } catch (err) {
      setError(err.message)
    }
  }

  // With sections frozen, say what Generate will keep and what it will build
  // before it starts.
  const [confirmGenerate, setConfirmGenerate] = useState(false)
  async function handleGenerate() {
    if ((frozenById.size > 0 || subjectFreezes.length > 0) && !confirmGenerate) {
      setConfirmGenerate(true)
      return
    }
    setConfirmGenerate(false)
    setError(null)
    try {
      await generate()
    } catch (err) {
      setError(err.message)
    }
  }

  // Patches the one (or two, for a swap) entries the server actually
  // returned into local state instead of re-fetching the whole timetable
  // — refetching every entry in the school just to reflect a single
  // lock/move/swap was the cause of the lock toggle visibly taking 5-10
  // seconds to show its new state (a school-wide timetable can be
  // hundreds of rows; PATCH/swap already return the exact row(s) that
  // changed, so there's nothing else here that could have gone stale).
  async function handleEditCommand(e) {
    e.preventDefault()
    const text = commandText.trim()
    if (!text) return
    setCommandSubmitting(true)
    setCommandFeedback(null)
    try {
      const result = await api.editTimetableByCommand(timetable.id, text)
      applyEntryUpdates(result)
      setCommandFeedback({ ok: true, text: result.description })
      setCommandText('')
    } catch (err) {
      setCommandFeedback({ ok: false, text: err.message })
    } finally {
      setCommandSubmitting(false)
    }
  }

  // Locks or unlocks everything in the clicked cell - a block's options are
  // pinned together, since they always run together. Anything already locked
  // counts as the slot being locked, so a click on a part-locked block frees
  // all of it rather than locking the rest.
  async function handleToggleLock(entries) {
    if (entries.length === 0) return
    setError(null)
    const { class_group_id: classGroupId, period_id: periodId } = entries[0]
    const locked = !entries.some((e) => e.locked)
    try {
      applyEntryUpdates(await api.lockSlot(timetable.id, classGroupId, periodId, locked))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDrop(day, order, classGroupId) {
    const source = dragSource
    setDragSource(null)
    if (!source) return
    // Every section's grid is on screen at once, so a drop can land in a grid
    // the dragged slot does not belong to. Moving it would quietly reposition
    // it inside its OWN section, which is not what dropping it over 8B looks
    // like it should do.
    if (source.classGroupId !== classGroupId) {
      setError("A slot can only be moved within its own section's timetable.")
      return
    }
    const targetPeriod = periodAt(day, order)
    if (!targetPeriod || targetPeriod.id === source.period.id) return // dropped back on itself
    if (kindOf(targetPeriod) !== 'lesson') {
      const what = { class_teacher: 'the class teacher period', zero: 'the zero period' }[kindOf(targetPeriod)]
      setError(`Nothing can be scheduled in ${what ?? 'a break'}.`)
      return
    }
    if (frozenById.has(classGroupId)) {
      setError('This section is frozen. Unfreeze it to change its timetable.')
      return
    }
    const section = classGroups.find((cg) => cg.id === classGroupId)
    if (section && isOffFor(targetPeriod, section)) {
      setError(`${section.grade}'s school day is over by then, so no lessons go there.`)
      return
    }
    if (section && isZeroFor(targetPeriod, section)) {
      setError(`That's ${section.grade ?? 'this section'}'s zero period - no lessons are scheduled in it.`)
      return
    }
    if (entriesFor(day, order, classGroupId).some((e) => e.locked)) {
      setError("That slot is locked. Unlock it before swapping something into it.")
      return
    }
    const frozenThere = entriesFor(day, order, classGroupId).find((e) => e.subject_frozen)
    if (frozenThere) {
      setError(`${frozenThere.subject_name} is frozen, so that lesson stays where it is. Unfreeze it under Freezing > Subjects to move it.`)
      return
    }
    setError(null)
    // The cells move now, not when the server answers. Waiting for the round
    // trip put a visible delay on every drag, on an interaction that should
    // feel like picking a card up and putting it down.
    //
    // Whatever was in the target comes back to where the dragged slot was, so
    // moving into a free cell, swapping two lessons and trading a block for a
    // lesson are one operation - and one request, which the server applies
    // all-or-nothing.
    //
    // `rollback` restores the cache if the server refuses - usually because
    // the target double-books a teacher - which is the only honest response to
    // a move that turned out not to be allowed.
    const rollback = optimisticSlotMove(classGroupId, source.period, targetPeriod)
    try {
      applyEntryUpdates(
        await api.moveSlot(timetable.id, classGroupId, source.period.id, targetPeriod.id),
      )
    } catch (err) {
      rollback()
      setError(err.message)
    }
  }

  const days = [...new Set(periods.map((p) => p.day_of_week))].sort((a, b) => a - b)
  const orders = [...new Set(periods.map((p) => p.order))].sort((a, b) => a - b)

  function periodAt(day, order) {
    return periods.find((p) => p.day_of_week === day && p.order === order)
  }

  // Returns every entry in this slot, not just one — a lab-batch-split
  // subject (Subject.lab_batch_count >= 2, see backend/app/services/
  // solver.py) produces several simultaneous entries at the same class
  // group + period, one per batch, each with its own teacher and room.
  // The normal, unsplit case is just an array of 0 or 1.
  function entriesFor(day, order, classGroupId = null) {
    const period = periodAt(day, order)
    if (!period || !timetable) return []
    if (classGroupId != null) {
      return timetable.entries.filter(
        (e) => e.period_id === period.id && e.class_group_id === classGroupId
      )
    }
    // Includes slots where this teacher is only the *assistant*, not the
    // main teacher — their own timetable should show both, not just the
    // classes they lead solo.
    // A class pooled from several sections is one lesson for its teacher.
    return teacherLessons(timetable.entries.filter(
      (e) =>
        e.period_id === period.id &&
        (e.teacher_id === selectedTeacherId || e.assistant_teacher_id === selectedTeacherId)
    ))
  }

  const classGroupName = (id) => classGroups.find((c) => c.id === id)?.name
  // "Class 6 - A", not "Sec A": a teacher takes sections in several grades,
  // and the section letter alone doesn't say which.
  const classGroupLabel = (id) => {
    const cg = classGroups.find((c) => c.id === id)
    return cg ? [cg.grade, cg.name].filter(Boolean).join(' - ') : ''
  }

  // What a slot is for: a lesson, a break, the class teacher period or a
  // whole-school zero period. Older responses only said is_break.
  const kindOf = (p) => p?.kind ?? (p?.is_break ? 'break' : 'lesson')

  // Only lessons are numbered, so the row after a class teacher period is
  // "Period 1" - the same numbers saved rules and the exports use.
  function rowLabel(order) {
    const here = periods.filter((p) => p.order === order)
    const lesson = here.find((p) => kindOf(p) === 'lesson')
    if (lesson) return `Period ${lesson.number ?? order + 1}`
    const kind = kindOf(here[0])
    if (kind === 'class_teacher') return 'Class teacher'
    if (kind === 'zero') return 'Zero period'
    return here.find((p) => p.label)?.label || 'Break'
  }

  // A zero period kept free for this section's grade (or everyone) on an
  // otherwise ordinary lesson slot.
  const isZeroFor = (period, cg) =>
    !!period && (period.zero_all || (cg.grade != null && (period.zero_grades ?? []).includes(cg.grade)))
  // This section's grade has a shorter day and has gone home by this slot.
  const isOffFor = (period, cg) => !!period && cg.grade != null && (period.off_grades ?? []).includes(cg.grade)

  // What a section's grid shows in a slot that isn't a lesson for it.
  function sectionSpecial(day, order, cg) {
    const period = periodAt(day, order)
    const kind = kindOf(period)
    if (kind === 'class_teacher') {
      const teacher = teachers.find((t) => t.id === cg.class_teacher_id)
      return teacher
        ? { text: teacher.name, tone: 'class_teacher' }
        : { text: 'No class teacher set', tone: 'warn' }
    }
    if (kind === 'zero') return { text: 'Zero period', tone: 'zero' }
    if (kind === 'break') return { text: period.label || 'Break', tone: 'muted' }
    if (isOffFor(period, cg) && entriesFor(day, order, cg.id).length === 0) {
      return { text: 'No class', tone: 'muted' }
    }
    // A lesson left there from before the zero period existed still shows.
    if (isZeroFor(period, cg) && entriesFor(day, order, cg.id).length === 0) {
      return { text: 'Zero period', tone: 'zero' }
    }
    return null
  }

  // The same for a teacher's grid: their own sections in the class teacher
  // period, and the school's breaks and zero period.
  function teacherSpecial(day, order) {
    const period = periodAt(day, order)
    const kind = kindOf(period)
    if (kind === 'class_teacher') {
      const own = classGroups.filter((cg) => cg.class_teacher_id === selectedTeacherId)
      return own.length
        ? { text: `Class teacher · ${own.map((cg) => (cg.grade ? `${cg.grade} ${cg.name}` : cg.name)).join(', ')}`, tone: 'class_teacher' }
        : { text: '', tone: 'muted' }
    }
    if (kind === 'zero') return { text: 'Zero period', tone: 'zero' }
    if (kind === 'break') return { text: period.label || 'Break', tone: 'muted' }
    return null
  }


  // In By Teacher view, an entry can show up because the selected teacher
  // is the main teacher or because they're only the assistant (see
  // entriesFor above) — this tells the two apart so the grid can label
  // "(Assisting)" instead of implying they're leading a class solo.
  const isSelectedTeacherAssisting = (e) =>
    view === 'teacher' && e.assistant_teacher_id === selectedTeacherId && e.teacher_id !== selectedTeacherId

  // Sections in the order the sidebar lists them, so scrolling and clicking
  // agree about what comes next.
  const sections = sortSections(classGroups)

  // Picking a section in the sidebar scrolls to it rather than swapping what
  // is on screen. The selection already exists and is already wired - this
  // just changes what it means here, so the sidebar needs no knowledge of the
  // timetable view.
  //
  // Deliberately not on first paint: arriving at the tab and being thrown past
  // the Generate button and the warnings above the grid is disorienting, and
  // the admin has not asked to go anywhere yet.
  const scrolledOnce = useRef(false)
  useEffect(() => {
    if (view !== 'section' || !classGroup) return
    if (!scrolledOnce.current) {
      scrolledOnce.current = true
      return
    }
    document
      .getElementById(sectionAnchorId(classGroup.id))
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [classGroup, view])

  const isGenerating = isSubmittingGenerate || timetable?.status === 'generating'
  // The failed run: the one on screen if there is no version to fall back on,
  // otherwise the failure newer than the current version.
  const failedRun = timetable?.status === 'failed' ? timetable : failureTimetable?.status === 'failed' ? failureTimetable : null
  const failed = !isGenerating && failedRun != null
  // The reasons open by themselves when a generation fails, once per failure.
  const [failureOpen, setFailureOpen] = useState(false)
  useEffect(() => {
    if (failed && failedRun && !seenFailures.has(failedRun.id)) setFailureOpen(true)
  }, [failed, failedRun])
  const solved = !isGenerating && timetable?.status === 'draft'
  // Rules this timetable currently breaks, computed server-side on every read
  // (see _violations_for in backend/app/routers/timetables.py). Normally
  // empty: the solver was given the same rules. It fills up when a slot is
  // moved by hand - a manual move that double-books nobody passes every
  // physical check while still breaking a rule, and without this the
  // Constraints tab goes on calling that rule enforced.
  //
  // Only RULES count as broken. A preference ("try to...") is allowed to give
  // way when it can't be fully met - that is what makes it a preference - so
  // it gets a calm note below rather than the warning, the cell markings and
  // the per-section counts.
  const allViolations = timetable?.violations ?? []
  const violations = allViolations.filter((v) => (v.strength ?? 'required') === 'required')
  const softViolations = allViolations.filter((v) => (v.strength ?? 'required') !== 'required')
  // One line per rule, however many places it's broken: a "spread evenly"
  // rule is checked per teacher, and listing each one buried the message.
  const groupByRule = (list) => {
    const byRule = new Map()
    for (const v of list) {
      const key = v.constraint_id ?? v.description
      const g = byRule.get(key) ?? { description: v.description, details: [] }
      g.details.push(v.detail)
      byRule.set(key, g)
    }
    return [...byRule.values()]
  }
  const brokenRules = groupByRule(violations)
  // Subjects nobody is qualified to teach yet are still placed, with no
  // teacher. Listed once each (subject in section), not once per lesson.
  const noTeacherYet = (() => {
    if (!solved) return []
    const label = (id) => {
      const cg = classGroups.find((c) => c.id === id)
      return cg ? [cg.grade, cg.name].filter(Boolean).join(' - ') : ''
    }
    const seen = new Map()
    for (const e of timetable?.entries ?? []) {
      if (e.teacher_id != null) continue
      const key = `${e.class_group_id}:${e.subject_id}`
      if (!seen.has(key)) seen.set(key, `${e.subject_name} in ${label(e.class_group_id)}`)
    }
    return [...seen.values()]
  })()
  const unmetPreferences = groupByRule(softViolations)
  // Which cells to mark. A slot can break more than one rule, so the entry id
  // maps to all of them rather than the first found.
  const violatingEntries = new Map()
  for (const v of violations) {
    for (const id of v.entry_ids) {
      violatingEntries.set(id, [...(violatingEntries.get(id) ?? []), v])
    }
  }

  // Counted in slots, not entries: a block breaking a rule is one cell to
  // move even when three of its options are named in the violation.
  const entryById = new Map((timetable?.entries ?? []).map((e) => [e.id, e]))
  const brokenSlots = new Set(
    [...violatingEntries.keys()]
      .map((id) => entryById.get(id))
      .filter(Boolean)
      .map((e) => `${e.class_group_id}:${e.period_id}`),
  )

  // With every section stacked, the band above the grid says what broke but
  // not where to scroll. This puts the count on the section's own heading.
  const sectionViolationCount = (classGroupId) =>
    [...brokenSlots].filter((key) => key.startsWith(`${classGroupId}:`)).length


  return (
    <div className="flex flex-col gap-5">
      <div className="inline-flex w-fit rounded-md border border-slate-300 p-0.5 text-xs">
        <button
          onClick={() => setPage('schedule')}
          className={`rounded px-3 py-1.5 font-medium ${page === 'schedule' ? 'bg-neutral-900 text-white' : 'text-slate-600'}`}
        >
          Schedule
        </button>
        <button
          onClick={() => setPage('substitutions')}
          className={`rounded px-3 py-1.5 font-medium ${page === 'substitutions' ? 'bg-neutral-900 text-white' : 'text-slate-600'}`}
        >
          Substitutions
        </button>
      </div>

      {page === 'substitutions' ? (
        <SubstitutionsTab schoolId={schoolId} classGroups={classGroups} teachers={teachers} readOnly={readOnly} />
      ) : (
        <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-medium">Generate timetable</h3>
          <p className="mt-1 text-sm text-slate-500">
            Solves for the whole school at once, so teachers shared across
            sections never overlap. Large schools can take up to a minute, 
            so feel free to switch tabs while it runs. In the By Section view
            you can drag a slot onto a free cell to move it, drag it onto
            another slot to swap the two, or click a slot to lock it in
            place before regenerating.  Locked slots are shown in red,
            unlocked ones in green. An elective block moves and locks as
            one slot, since its subjects always run together.
          </p>
        </div>
        {!readOnly && (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleGenerate}
            disabled={isGenerating}
            className="flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {isGenerating ? 'Generating…' : 'Generate Timetable'}
          </motion.button>
        )}
      </div>

      <div className="h-px bg-slate-200" />

      {violations.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-none">
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
            <path d="M12 9v4" />
            <path d="M12 17h.01" />
          </svg>
          <div className="flex flex-col gap-1">
            <span className="font-medium">
              {brokenRules.length === 1 ? '1 rule you set is' : `${brokenRules.length} rules you set are`} broken
              {' '}in {brokenSlots.size === 1 ? '1 slot' : `${brokenSlots.size} slots`}
            </span>
            {/* The rule's own confirmed sentence, not a paraphrase - it is what
                the Constraints tab shows, and a warning that named it
                differently would send someone looking for a rule they don't
                have. The numbers say which slot to move. */}
            <ul className="flex flex-col gap-0.5">
              {brokenRules.map((r) => (
                <li key={r.description}>
                  {r.description}{' '}
                  <span className="text-amber-700">
                    ({r.details[0]}
                    {r.details.length > 1 ? `, and ${r.details.length - 1} more` : ''})
                  </span>
                </li>
              ))}
            </ul>
            <span className="text-amber-700">
              The change is kept. Move the marked slots back, or change the rule on the
              Constraints tab.
            </span>
          </div>
        </div>
      )}

      {unmetPreferences.length > 0 && (
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2.5 text-sm text-sky-900">
          <p className="font-medium">
            {unmetPreferences.length === 1 ? '1 preference' : `${unmetPreferences.length} preferences`} couldn&rsquo;t be
            fully met everywhere
          </p>
          <ul className="mt-1 flex flex-col gap-0.5 text-sky-800">
            {unmetPreferences.map((p) => (
              <li key={p.description}>
                {p.description}{' '}
                <span className="text-sky-700">
                  (not met in {p.details.length} {p.details.length === 1 ? 'case' : 'cases'}, e.g. {p.details[0]})
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-sky-700">
            That&rsquo;s allowed for a preference: the timetable follows it as far as it can. If one must always hold,
            reword it on the Constraints tab without &ldquo;try to&rdquo; to make it a rule.
          </p>
        </div>
      )}

      {confirmGenerate && (
        <GenerateConfirm
          sections={sections}
          frozenById={frozenById}
          subjectFreezes={subjectFreezes}
          onCancel={() => setConfirmGenerate(false)}
          onConfirm={handleGenerate}
        />
      )}

      {solved && (
        <p className="text-sm text-slate-600">
          Showing <span className="font-medium text-slate-900">{versionLabel(timetable)}</span>
          {timetable.created_at && (
            <span className="text-slate-400"> · generated {new Date(timetable.created_at).toLocaleString()}</span>
          )}
          . Edits here change this version. Open, rename or delete versions on the Dashboard.
        </p>
      )}

      {solved && (timetable?.generation_notes?.length > 0 || timetable?.frozen_kept?.length > 0) && (
        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-800">
          {timetable.frozen_kept?.length > 0 && (
            <p>
              <span className="font-medium">Kept as frozen:</span> {timetable.frozen_kept.join(', ')}. Their timetables
              weren&rsquo;t regenerated.
            </p>
          )}
          {timetable.generation_notes?.length > 0 && (
            <>
              <p className={`font-medium ${timetable.frozen_kept?.length ? 'mt-1.5' : ''}`}>From this generation</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-slate-700">
                {timetable.generation_notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {noTeacherYet.length > 0 && (
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2.5 text-sm text-sky-900">
          <p className="font-medium">
            {noTeacherYet.length === 1 ? '1 subject has' : `${noTeacherYet.length} subjects have`} no teacher yet
          </p>
          <p className="mt-1 text-sky-800">
            {noTeacherYet.slice(0, 8).join(', ')}
            {noTeacherYet.length > 8 ? `, and ${noTeacherYet.length - 8} more` : ''}.
          </p>
          <p className="mt-1 text-xs text-sky-700">
            Their lessons are in the timetable, marked &ldquo;No teacher yet&rdquo;. Add a teacher qualified for them
            on the Data Entry tab and generate again to fill them in.
          </p>
        </div>
      )}

      {unenforcedConstraints.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-none">
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
            <path d="M12 9v4" />
            <path d="M12 17h.01" />
          </svg>
          <span>
            {unenforcedConstraints.length === 1
              ? "1 saved constraint isn't applied when generating"
              : `${unenforcedConstraints.length} saved constraints aren't applied when generating`}
            , so the timetable below won't reflect{' '}
            {unenforcedConstraints.length === 1 ? 'it' : 'them'}. Check the Constraints tab for
            which ones and why.
          </span>
        </div>
      )}

      {isGenerating && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
          className="flex flex-col items-center justify-center gap-3 py-16 text-sm text-slate-500"
        >
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
          Solving the schedule. This runs in the background, so it's safe
          to keep working elsewhere and come back.
        </motion.div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      {failed && (
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
          <span className="inline-flex items-center gap-1.5 font-medium text-red-700">
            <span className="h-1.5 w-1.5 rounded-full bg-red-600" aria-hidden="true" />
            The last generation couldn&rsquo;t build a timetable.
          </span>
          {timetable?.status === 'draft' && (
            <span className="text-slate-500">You&rsquo;re still working from {versionLabel(currentVersion ?? timetable)}.</span>
          )}
          <button
            onClick={() => setFailureOpen(true)}
            className="font-medium text-neutral-900 underline underline-offset-2 hover:text-neutral-600"
          >
            See why
          </button>
        </div>
      )}

      <GenerationFailedDialog
        open={failed && failureOpen}
        explanation={failedRun?.error_explanation}
        message={failedRun?.error_message}
        onClose={() => {
          if (failedRun) seenFailures.add(failedRun.id)
          setFailureOpen(false)
        }}
        onOpenConstraints={onOpenConstraints}
      />

      {solved && (
        <motion.div
          key={timetable.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex rounded-md border border-slate-300 p-0.5 text-xs">
                <button
                  onClick={() => setView('section')}
                  className={`rounded px-3 py-1 ${view === 'section' ? 'bg-neutral-900 text-white' : 'text-slate-600'}`}
                >
                  By Section
                </button>
                <button
                  onClick={() => setView('teacher')}
                  className={`rounded px-3 py-1 ${view === 'teacher' ? 'bg-neutral-900 text-white' : 'text-slate-600'}`}
                >
                  By Teacher
                </button>
              </div>
              {view === 'teacher' && (
                <SearchableSelect
                  ariaLabel="Teacher"
                  value={selectedTeacherId}
                  onChange={setSelectedTeacherId}
                  options={teachers.map((t) => ({ value: t.id, label: t.name }))}
                  className="min-w-[10rem]"
                />
              )}
            </div>

            <div className="flex items-center gap-2 text-xs">
              <label
                className="mr-1 flex cursor-pointer select-none items-center gap-1.5 text-slate-600"
                title="Adds the Timetablz name to the header and footer of every page"
              >
                <input
                  type="checkbox"
                  checked={watermark}
                  onChange={(e) => toggleWatermark(e.target.checked)}
                  className="h-3.5 w-3.5 accent-neutral-900"
                />
                Timetablz watermark
                {!cleanExportsAllowed && (
                  <span className="rounded bg-neutral-900 px-1 py-px text-[10px] font-semibold uppercase tracking-wide text-white">
                    Pro to remove
                  </span>
                )}
              </label>
              <span className="text-slate-400">Export:</span>
              <button
                onClick={() => handleExport('xlsx')}
                disabled={!!exporting}
                className="rounded-md border border-slate-300 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
              >
                {exporting === 'xlsx' ? 'Preparing…' : 'Excel'}
              </button>
              <button
                onClick={() => handleExport('pdf')}
                disabled={!!exporting}
                className="rounded-md border border-slate-300 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
              >
                {exporting === 'pdf' ? 'Preparing…' : 'PDF'}
              </button>
            </div>
          </div>

          {view === 'section' && !readOnly && (
            <div className="flex flex-col gap-1.5">
              <form onSubmit={handleEditCommand} className="flex items-center gap-2.5 rounded-md border border-slate-300 py-1.5 pl-3.5 pr-1.5">
                <span className="text-slate-400">✦</span>
                <input
                  value={commandText}
                  onChange={(e) => setCommandText(e.target.value)}
                  placeholder="Or describe an edit, e.g. move Math to period 2 on Wednesday, or lock Mrs. Sharma's Monday classes"
                  className="flex-1 py-1 text-sm focus:outline-none"
                />
                <button
                  disabled={commandSubmitting}
                  className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
                >
                  {commandSubmitting ? 'Applying…' : 'Apply'}
                </button>
              </form>
              {commandFeedback && (
                <p className={`text-xs ${commandFeedback.ok ? 'text-emerald-700' : 'text-red-600'}`}>
                  {commandFeedback.text}
                </p>
              )}
            </div>
          )}

          {view === 'section' ? (
            // Every section, stacked and scrollable, rather than one at a
            // time. Picking a section in the sidebar scrolls to it instead of
            // swapping what is on screen - the whole school is one document,
            // which is how a timetable is read on paper and how it gets
            // checked against itself.
            <div className="flex flex-col gap-8">
              <section aria-label="Freezing" className="flex flex-col gap-3 rounded-md border border-sky-200 bg-sky-50/40 p-3">
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className="text-sm font-semibold text-sky-900">❄ Freezing</h3>
                  <div role="tablist" aria-label="Freeze by" className="flex gap-1">
                    {[
                      ['sections', 'Sections', frozenById.size],
                      ['subjects', 'Subjects', subjectFreezes.length],
                    ].map(([id, label, count]) => (
                      <button
                        key={id}
                        type="button"
                        role="tab"
                        aria-selected={freezeTab === id}
                        onClick={() => setFreezeTab(id)}
                        className={`rounded-full px-3 py-0.5 text-sm ${
                          freezeTab === id ? 'bg-sky-800 text-white' : 'text-sky-900 hover:bg-sky-100'
                        }`}
                      >
                        {label}{count > 0 ? ` (${count})` : ''}
                      </button>
                    ))}
                  </div>
                </div>
                {freezeTab === 'sections' ? (
                  frozenById.size > 0 ? (
                    <FrozenSummary sections={sections} frozenById={frozenById} />
                  ) : (
                    <p className="text-sm text-slate-600">
                      No sections are frozen.{!readOnly && ' Freeze one with the Freeze button beside its timetable, or a whole grade from its heading.'}
                    </p>
                  )
                ) : (
                  <SubjectFreezePanel
                    freezes={subjectFreezes}
                    entries={timetable.entries}
                    sections={sections}
                    canFreeze={!readOnly}
                    busy={subjectFreezing.isSaving}
                    onFreeze={subjectFreezing.freeze}
                    onUnfreeze={subjectFreezing.unfreeze}
                  />
                )}
              </section>
              {sections.map((cg, i) => (
                <div key={cg.id} className="flex flex-col gap-3">
                {cg.grade && cg.grade !== sections[i - 1]?.grade && (
                  <GradeFreezeRow
                    grade={cg.grade}
                    sections={sections.filter((s) => s.grade === cg.grade)}
                    frozenById={frozenById}
                    canFreeze={!readOnly}
                    busy={freezing}
                    onFreeze={handleFreeze}
                  />
                )}
                <SectionTimetable
                  classGroup={cg}
                  frozen={frozenById.get(cg.id) ?? null}
                  canFreeze={!readOnly}
                  freezing={freezing}
                  onToggleFreeze={() => handleFreeze([cg.id], !frozenById.has(cg.id))}
                  timetableId={timetable.id}
                  watermark={watermark}
                  combinations={combinationsFor(electiveBlocks, cg.id, subjectName)}
                  violationCount={sectionViolationCount(cg.id)}
                  onError={setError}
                  days={days}
                  orders={orders}
                  periodAt={periodAt}
                  entriesAt={(d, o) => entriesFor(d, o, cg.id)}
                  editable={!readOnly}
                  violatingEntries={violatingEntries}
                  onDragStart={(d, o) => setDragSource({ classGroupId: cg.id, period: periodAt(d, o) })}
                  onDragEnd={() => setDragSource(null)}
                  onDrop={(d, o) => handleDrop(d, o, cg.id)}
                  onToggleLock={handleToggleLock}
                  rowLabel={rowLabel}
                  specialCell={(d, o) => sectionSpecial(d, o, cg)}
                />
                </div>
              ))}
            </div>
          ) : (
            <ScheduleGrid
              days={days}
              orders={orders}
              periodAt={periodAt}
              entriesAt={(d, o) => entriesFor(d, o)}
              editable={false}
              violatingEntries={violatingEntries}
              onDragStart={() => {}}
              onDragEnd={() => {}}
              onDrop={() => {}}
              onToggleLock={() => {}}
              secondaryLine={(e) =>
                `${(e.class_group_ids ?? [e.class_group_id]).map(classGroupLabel).join(', ')}${
                  isSelectedTeacherAssisting(e) ? ' (Assisting)' : ''
                }`
              }
              showAssistant={false}
              rowLabel={rowLabel}
              specialCell={teacherSpecial}
            />
          )}
        </motion.div>
      )}

      {!isGenerating && !timetable && (
        <div className="flex flex-col items-center justify-center gap-1 py-16 text-center text-slate-500">
          <p className="text-sm">No timetable generated yet for this school.</p>
          <p className="text-xs">Add subjects and constraints, then hit Generate.</p>
        </div>
      )}
        </>
      )}
    </div>
  )
}

/**
 * One section's week, with what each of its students actually attends.
 *
 * A section with elective blocks has one timetable on paper but several in
 * practice: the Physics + Chemistry student and the Accounts + Economics one
 * sit in different rooms during every block. Picking a combination filters
 * the grid to the common subjects plus the chosen option from each block -
 * the same filter the student export prints, in the same order (see
 * src/studentCombinations.js), so "3." here is sheet 3 there.
 *
 * A student's view is read-only. Dragging in it would still move the whole
 * block, which is not what dragging the one subject on screen looks like it
 * should do.
 */
/**
 * What generating will and won't change, said once above the sections.
 * Whole grades are named as grades, so "Grades 11-12 frozen" reads at a
 * glance instead of a list of every section in them.
 */
/** "Grade 1, Grade 2, Grade 3 · A": whole grades named once, the rest by section. */
function summariseSections(sections, include) {
  const picked = sections.filter((cg) => include(cg))
  const names = []
  const seen = new Set()
  for (const cg of picked) {
    if (cg.grade && seen.has(cg.grade)) continue
    if (cg.grade && sections.filter((s) => s.grade === cg.grade).every(include)) {
      names.push(cg.grade)
      seen.add(cg.grade)
      continue
    }
    names.push(cg.grade ? `${cg.grade} · ${cg.name}` : cg.name)
  }
  return { names, count: picked.length }
}

/** Before generating with sections frozen: what is kept, from which version, and what is built. */
function GenerateConfirm({ sections, frozenById, subjectFreezes = [], onCancel, onConfirm }) {
  const kept = summariseSections(sections, (cg) => frozenById.has(cg.id))
  const built = summariseSections(sections, (cg) => !frozenById.has(cg.id))
  const sources = [...new Set([...frozenById.values()].map((f) => f.frozen_from).filter(Boolean))]
  const stale = [...frozenById.values()].filter((f) => f.stale_reason).length
  const staleSubjects = subjectFreezes.filter((f) => f.stale_reasons.length > 0)
  return (
    <div role="dialog" aria-modal="true" aria-label="Generate a new version"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
        <h3 className="text-base font-semibold">Generate a new version?</h3>
        <dl className="mt-3 flex flex-col gap-2 text-sm">
          {kept.count > 0 && (
            <div>
              <dt className="font-medium text-slate-900">Keeping, exactly as they are</dt>
              <dd className="text-slate-700">
                {kept.names.join(', ')} ({kept.count} section{kept.count === 1 ? '' : 's'}, frozen
                {sources.length ? ` from ${sources.join(' and ')}` : ''})
              </dd>
            </div>
          )}
          {subjectFreezes.length > 0 && (
            <div>
              <dt className="font-medium text-slate-900">Keeping these subjects&rsquo; lessons where they are</dt>
              <dd className="text-slate-700">
                {subjectFreezes
                  .map((f) => `${f.subject} (${f.scope_label}${f.frozen_from ? `, from ${f.frozen_from}` : ''})`)
                  .join('; ')}
              </dd>
            </div>
          )}
          <div>
            <dt className="font-medium text-slate-900">Building</dt>
            <dd className="text-slate-700">
              {built.count ? `${built.names.join(', ')} (${built.count} section${built.count === 1 ? '' : 's'})` : 'Nothing - every section is frozen.'}
            </dd>
          </div>
        </dl>
        {staleSubjects.length > 0 && (
          <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-800">
            {staleSubjects.map((f) => f.subject).join(', ')} changed since freezing, so generating will stop.
            Unfreeze {staleSubjects.length === 1 ? 'it' : 'them'} first.
          </p>
        )}
        {stale > 0 && (
          <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">
            {stale} frozen section{stale === 1 ? ' has' : 's have'} changed since freezing. They&rsquo;ll still be kept as
            they were; unfreeze them to rebuild with the change.
          </p>
        )}
        <p className="mt-3 text-xs text-slate-500">The result is a new version. Earlier versions stay on the Dashboard.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onCancel}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Cancel
          </button>
          <button type="button" onClick={onConfirm}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700">
            Generate
          </button>
        </div>
      </div>
    </div>
  )
}

function FrozenSummary({ sections, frozenById }) {
  const frozen = sections.filter((cg) => frozenById.has(cg.id))
  if (frozen.length === 0) return null
  const names = []
  const seen = new Set()
  for (const cg of frozen) {
    if (cg.grade && !seen.has(cg.grade)) {
      const grade = sections.filter((s) => s.grade === cg.grade)
      if (grade.every((s) => frozenById.has(s.id))) {
        names.push(cg.grade)
        seen.add(cg.grade)
        continue
      }
    }
    if (!cg.grade || !seen.has(cg.grade)) names.push(cg.grade ? `${cg.grade} · ${cg.name}` : cg.name)
  }
  const others = sections.length - frozen.length
  return (
    <div className="flex items-start gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">
      <span aria-hidden="true">❄</span>
      <span>
        Frozen: {names.join(', ')} ({frozen.length} section{frozen.length === 1 ? '' : 's'}
        {(() => {
          const from = [...new Set(frozen.map((cg) => frozenById.get(cg.id)?.frozen_from).filter(Boolean))]
          return from.length ? `, from ${from.join(' and ')}` : ''
        })()}
        ). Generating keeps{' '}
        {frozen.length === 1 ? 'it' : 'them'} exactly as {frozen.length === 1 ? 'it is' : 'they are'}
        {others > 0
          ? ` and only changes the other ${others}.`
          : ' - every section is frozen, so nothing will change.'}
      </span>
    </div>
  )
}

/** A grade's heading, with freezing or unfreezing all of its sections at once. */
function GradeFreezeRow({ grade, sections, frozenById, canFreeze, busy, onFreeze }) {
  const allFrozen = sections.every((s) => frozenById.has(s.id))
  return (
    <div className="flex items-center justify-between gap-2 border-b border-slate-200 pb-1">
      <h3 className="text-sm font-semibold text-slate-800">{grade}</h3>
      {canFreeze && (
        <button
          type="button"
          disabled={busy}
          onClick={() => onFreeze(sections.map((s) => s.id), !allFrozen)}
          className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {allFrozen ? `Unfreeze all of ${grade}` : `Freeze all of ${grade}`}
        </button>
      )}
    </div>
  )
}

function SectionTimetable({
  classGroup,
  // { frozen_at, stale_reason } when frozen, null otherwise.
  frozen = null,
  canFreeze = false,
  freezing = false,
  onToggleFreeze,
  timetableId,
  // [] - no blocks, the same for everyone; null - too many to list.
  combinations,
  violationCount,
  onError,
  watermark = true,
  entriesAt,
  editable,
  ...gridProps
}) {
  const [studentIndex, setStudentIndex] = useState('') // '' = the whole section
  const [exporting, setExporting] = useState(null) // null | 'xlsx' | 'pdf'
  const combination =
    studentIndex === '' || !combinations ? null : combinations[Number(studentIndex)] ?? null
  const label = classGroup.grade ? `${classGroup.grade} · ${classGroup.name}` : classGroup.name

  async function handleStudentExport(format) {
    if (exporting) return
    setExporting(format)
    try {
      await api.downloadStudentTimetables(
        timetableId,
        format,
        classGroup.id,
        classGroup.grade ? `${classGroup.grade} ${classGroup.name}` : classGroup.name,
        { watermark },
      )
    } catch (err) {
      onError(err.message)
    } finally {
      setExporting(null)
    }
  }

  return (
    <section
      id={sectionAnchorId(classGroup.id)}
      aria-label={label}
      // Clears the sticky header when the sidebar scrolls here.
      className={`flex scroll-mt-6 flex-col gap-2 ${
        frozen ? 'rounded-md bg-sky-50/50 p-2 ring-1 ring-sky-200' : ''
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-medium text-slate-700">
          {label}
          {frozen && (
            <span className="ml-2 rounded bg-sky-100 px-1.5 py-0.5 text-xs font-normal text-sky-900">
              ❄ Frozen
            </span>
          )}
          {violationCount > 0 && (
            <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-900">
              {violationCount} slot{violationCount === 1 ? '' : 's'} breaking a rule
            </span>
          )}
        </h4>
        {canFreeze && (
          <button
            type="button"
            disabled={freezing}
            onClick={onToggleFreeze}
            title={
              frozen
                ? 'Let the next Generate change this section again'
                : 'Keep this section exactly as it is when generating again'
            }
            className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {frozen ? 'Unfreeze' : 'Freeze'}
          </button>
        )}
        {combinations === null && (
          <span className="text-xs text-slate-400">
            This section's blocks allow more than {MAX_COMBINATIONS} subject combinations. Check
            them for a mistake.
          </span>
        )}
        {combinations?.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <label className="flex items-center gap-1.5 text-slate-500">
              Show
              <select
                aria-label={`Whose timetable to show for ${label}`}
                value={studentIndex}
                onChange={(e) => setStudentIndex(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700"
              >
                <option value="">Whole section (every option)</option>
                {combinations.map((c, i) => (
                  <option key={c.label + i} value={i}>
                    {i + 1}. {c.label}
                  </option>
                ))}
              </select>
            </label>
            <span className="text-slate-400">Student timetables:</span>
            <button
              onClick={() => handleStudentExport('xlsx')}
              disabled={!!exporting}
              className="rounded-md border border-slate-300 px-2.5 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
            >
              {exporting === 'xlsx' ? 'Preparing…' : 'Excel'}
            </button>
            <button
              onClick={() => handleStudentExport('pdf')}
              disabled={!!exporting}
              className="rounded-md border border-slate-300 px-2.5 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
            >
              {exporting === 'pdf' ? 'Preparing…' : 'PDF'}
            </button>
          </div>
        )}
      </div>
      {frozen?.stale_reason && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs text-amber-900">
          {frozen.stale_reason}
        </p>
      )}
      <ScheduleGrid
        {...gridProps}
        entriesAt={
          combination ? (d, o) => entriesAt(d, o).filter((e) => keeps(combination, e)) : entriesAt
        }
        // Frozen means nothing moves it - not a drag, not a lock.
        editable={editable && !combination && !frozen}
        secondaryLine={(e) => e.teacher_name ?? 'No teacher yet'}
        showAssistant
        showBlockName={!combination}
      />
    </section>
  )
}
