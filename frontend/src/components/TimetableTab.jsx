import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { api } from '../api'
import ScheduleGrid from './ScheduleGrid.jsx'
import {
  useApplyEntryUpdates,
  useElectiveBlocks,
  useOptimisticSlotMove,
  useGenerateTimetable,
  useTimetable,
  useTimetables,
} from '../hooks/useSchoolData'
import { combinationsFor, keeps, MAX_COMBINATIONS } from '../studentCombinations'
import SubstitutionsTab from './SubstitutionsTab'

// Where the sidebar scrolls to. Derived from the id rather than passed around,
// so selecting a section needs no extra wiring between the two components.
const sectionAnchorId = (classGroupId) => `timetable-section-${classGroupId}`

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
  const [selectedTeacherId, setSelectedTeacherId] = useState(teachers[0]?.id ?? null)
  const [error, setError] = useState(null)
  // Where the dragged slot came from: { classGroupId, period }. The section
  // is kept so a drop into another section's grid can be refused rather than
  // quietly moving the slot inside its own.
  const [dragSource, setDragSource] = useState(null)
  // Which export format is currently downloading, if any — guards against
  // a double-click firing two downloads with no visual feedback either way.
  const [exporting, setExporting] = useState(null) // null | 'xlsx' | 'pdf'
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
      await api.downloadTimetableExport(timetable.id, format)
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
    if (!stillValid) setSelectedTeacherId(teachers[0]?.id ?? null)
  }, [teachers, selectedTeacherId])

  // The latest timetable for this school, polled by useTimetable while the
  // solver is still working. Replaces App.jsx's setInterval + ref: the
  // interval is derived from the row's status, so it stops on its own and
  // resumes by itself after a reload mid-generation.
  const { data: timetableList = [] } = useTimetables(schoolId)
  // No created_at on TimetableOut - ids are assigned in creation order, so
  // the highest id is the most recent.
  const latestTimetableId =
    timetableList.length > 0 ? timetableList.reduce((a, b) => (b.id > a.id ? b : a)).id : null
  const { data: timetable = null } = useTimetable(latestTimetableId)
  const { generate, isGenerating: isSubmittingGenerate } = useGenerateTimetable(schoolId)
  const applyEntryUpdates = useApplyEntryUpdates(timetable?.id)
  const optimisticSlotMove = useOptimisticSlotMove(timetable?.id)
  const { data: electiveBlocks = [] } = useElectiveBlocks(schoolId)
  const subjectName = (id) => subjects.find((s) => s.id === id)?.name ?? '?'

  async function handleGenerate() {
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
    if (targetPeriod.is_break) {
      setError('Nothing can be scheduled in a break.')
      return
    }
    if (entriesFor(day, order, classGroupId).some((e) => e.locked)) {
      setError("That slot is locked — unlock it before swapping something into it.")
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
    return timetable.entries.filter(
      (e) =>
        e.period_id === period.id &&
        (e.teacher_id === selectedTeacherId || e.assistant_teacher_id === selectedTeacherId)
    )
  }

  const classGroupName = (id) => classGroups.find((c) => c.id === id)?.name


  // In By Teacher view, an entry can show up because the selected teacher
  // is the main teacher or because they're only the assistant (see
  // entriesFor above) — this tells the two apart so the grid can label
  // "(Assisting)" instead of implying they're leading a class solo.
  const isSelectedTeacherAssisting = (e) =>
    view === 'teacher' && e.assistant_teacher_id === selectedTeacherId && e.teacher_id !== selectedTeacherId

  // Sections in the order the sidebar lists them, so scrolling and clicking
  // agree about what comes next.
  const sections = [...classGroups].sort(
    (a, b) =>
      (a.grade ?? '').localeCompare(b.grade ?? '', undefined, { numeric: true }) ||
      (a.name ?? '').localeCompare(b.name ?? '', undefined, { numeric: true }),
  )

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
  const failed = !isGenerating && timetable?.status === 'failed'
  const solved = !isGenerating && timetable?.status === 'draft'
  // Rules this timetable currently breaks, computed server-side on every read
  // (see _violations_for in backend/app/routers/timetables.py). Normally
  // empty: the solver was given the same rules. It fills up when a slot is
  // moved by hand - a manual move that double-books nobody passes every
  // physical check while still breaking a rule, and without this the
  // Constraints tab goes on calling that rule enforced.
  const violations = timetable?.violations ?? []
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
        <SubstitutionsTab schoolId={schoolId} classGroups={classGroups} teachers={teachers} />
      ) : (
        <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-medium">Generate timetable</h3>
          <p className="mt-1 text-sm text-slate-500">
            Solves for the whole school at once, so teachers shared across
            sections never overlap. Large schools can take up to a minute —
            feel free to switch tabs while it runs. In the By Section view
            you can drag a slot onto a free cell to move it, drag it onto
            another slot to swap the two, or click a slot to lock it in
            place before regenerating — locked slots are shown in red,
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
              {brokenSlots.size === 1
                ? '1 slot now breaks a rule you set'
                : `${brokenSlots.size} slots now break rules you set`}
            </span>
            {/* The rule's own confirmed sentence, not a paraphrase - it is what
                the Constraints tab shows, and a warning that named it
                differently would send someone looking for a rule they don't
                have. The numbers say which slot to move. */}
            <ul className="flex flex-col gap-0.5">
              {violations.map((v, i) => (
                <li key={`${v.constraint_id}-${i}`}>
                  {v.description}{' '}
                  <span className="text-amber-700">— {v.detail}</span>
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
            {' '}— the timetable below won't reflect{' '}
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
          Solving the schedule — this runs in the background, so it's safe
          to keep working elsewhere and come back.
        </motion.div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      {failed && (
        <div className="max-w-xl rounded-lg border border-amber-300 bg-amber-50 p-5">
          <div className="font-medium text-amber-900">
            We couldn't build a conflict-free timetable
          </div>
          {/* error_explanation is a plain-language rewrite of error_message
              generated once at failure time (see
              backend/app/services/infeasibility_explainer.py) — shown as
              the lead sentence when available, with the raw technical
              causes still underneath (behind a toggle) for anyone who
              wants the precise detail. Null whenever that service didn't
              run (no ANTHROPIC_API_KEY) or wasn't applicable, in which
              case this falls back to showing just the raw list, same as
              before this existed. */}
          {timetable.error_explanation && (
            <p className="mt-2 text-sm text-amber-900">{timetable.error_explanation}</p>
          )}
          {/* error_message is newline-joined when the solver diagnosed one
              or more specific causes (see _diagnose_infeasibility in
              backend/app/services/solver.py) — rendered as a list so each
              cause reads as its own point instead of a run-on sentence. */}
          {(() => {
            const lines = (timetable.error_message || 'Generation failed for an unknown reason.')
              .split('\n')
              .filter(Boolean)
            const details = lines.length > 1 ? (
              <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800">
                {lines.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-amber-800">{lines[0]}</p>
            )

            if (!timetable.error_explanation) {
              return <div className="mt-2">{details}</div>
            }
            // The friendly explanation is already shown above, so the raw
            // detail is secondary here — tucked behind <details> instead
            // of always-visible, so the common case (read the friendly
            // sentence, fix it, move on) isn't cluttered by jargon most
            // admins won't need.
            return (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-medium text-amber-700 hover:text-amber-900">
                  Show technical detail
                </summary>
                <div className="mt-1.5">{details}</div>
              </details>
            )
          })()}
        </div>
      )}

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
                <select
                  value={selectedTeacherId ?? ''}
                  onChange={(e) => setSelectedTeacherId(Number(e.target.value))}
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                >
                  {teachers.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="flex items-center gap-2 text-xs">
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
              {sections.map((cg) => (
                <SectionTimetable
                  key={cg.id}
                  classGroup={cg}
                  timetableId={timetable.id}
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
                />
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
                `Sec ${classGroupName(e.class_group_id)}${
                  isSelectedTeacherAssisting(e) ? ' (Assisting)' : ''
                }`
              }
              showAssistant={false}
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
function SectionTimetable({
  classGroup,
  timetableId,
  // [] - no blocks, the same for everyone; null - too many to list.
  combinations,
  violationCount,
  onError,
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
      // Clears the sticky header when the sidebar scrolls here.
      className="flex scroll-mt-6 flex-col gap-2"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-medium text-slate-700">
          {label}
          {violationCount > 0 && (
            <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-900">
              {violationCount} slot{violationCount === 1 ? '' : 's'} breaking a rule
            </span>
          )}
        </h4>
        {combinations === null && (
          <span className="text-xs text-slate-400">
            This section's blocks allow more than {MAX_COMBINATIONS} subject combinations — check
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
      <ScheduleGrid
        {...gridProps}
        entriesAt={
          combination ? (d, o) => entriesAt(d, o).filter((e) => keeps(combination, e)) : entriesAt
        }
        editable={editable && !combination}
        secondaryLine={(e) => e.teacher_name}
        showAssistant
        showBlockName={!combination}
      />
    </section>
  )
}
