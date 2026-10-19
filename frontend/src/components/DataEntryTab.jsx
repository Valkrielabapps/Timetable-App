import { useEffect, useState } from 'react'
import { api } from '../api'
import BulkImportPanel from './BulkImportPanel'
import { confirmDialog } from './confirmDialog'
import TimetableStructurePanel from './TimetableStructurePanel'
import RoomsPanel from './RoomsPanel'
import {
  useElectiveBlockMutations,
  useElectiveBlocks,
  useRoomMutations,
  useRooms,
} from '../hooks/useSchoolData'
import ElectiveBlocksPanel from './ElectiveBlocksPanel'
import { DEFAULT_STRUCTURE } from '../timetableStructure'
import SetupExtractionPanel from './SetupExtractionPanel'
import SubjectsSection from './SubjectsSection'
import TeachersSection from './TeachersSection'

/**
 * Data Entry is four separate sub-pages, not one combined table:
 * Subjects (what the school teaches), Teachers (who teaches, and which
 * subjects they cover), Setup (periods and rooms — the foundational,
 * one-time setup a school does before entering subjects/teachers), and
 * This section's plan (how many periods/week the *currently selected*
 * section needs of each subject, plus which teacher covers it here).
 * Subjects/Teachers/Setup are reached from the sidebar's "Subjects &
 * Teachers" item (school-wide, no section implied); the Plan page is
 * reached by clicking a section in the sidebar directly — it has no
 * sub-nav tab of its own, since "click a section to see its plan"
 * already is the navigation for it, and showing the school-wide
 * Subjects/Teachers/Setup tabs while a specific section's plan is open
 * just invited the "why does the sidebar say Section 8-B while I'm
 * looking at every teacher in the school" confusion this split is meant
 * to avoid.
 *
 * Setup used to be a collapsed "Setup — N periods, N rooms — manage"
 * disclosure sitting above the Subjects/Teachers sub-nav — easy to miss
 * entirely for a new admin, since nothing about a plain underlined text
 * link says "this is where you configure the school's daily schedule."
 * It's now a full sub-page, a peer of Subjects and Teachers, since
 * periods/rooms are exactly as much "a point of data entry" as those two
 * are — a school can't get a working timetable without them.
 *
 * This used to be a single dense table where every row did five things
 * at once — subject name, room type/credits, periods/week, teacher
 * assignment, preferred-teacher picker, status — which meant "add
 * subjects" and "add teachers" (two genuinely separate tasks for a
 * school admin) were smashed into one screen. Splitting them mirrors how
 * an admin actually thinks about the job ("what do we teach" vs "who
 * teaches" vs "how much does this class need"), and lets each page have
 * its own prominent, correctly-scoped bulk import instead of one import
 * panel with a "which resource am I uploading" dropdown.
 *
 * Only "This section's plan" is genuinely scoped to `classGroupId` —
 * Subjects and Teachers are school-wide. `activeSectionId` on the Plan
 * page can be switched independently of the sidebar's selection (see
 * its own comment below), same as before the split.
 *
 * Periods and Rooms are still shared, foundational setup that doesn't
 * belong to Subjects or Teachers specifically, so they stay above the
 * sub-nav, visible regardless of which sub-page is active.
 */
export default function DataEntryTab({
  schoolId,
  classGroupId,
  institutionType,
  // Subjects/teachers/periods/rooms/classGroups are owned by App.jsx now,
  // not fetched here — this component gets unmounted every time the
  // admin switches to another top-level tab, so state kept locally here
  // was destroyed and had to be re-fetched from scratch on the way back.
  // App.jsx never unmounts, so lifting ownership there means switching
  // tabs and coming back to Data Entry shows the same data instantly,
  // with no re-fetch at all.
  subjects,
  setSubjects,
  teachers,
  setTeachers,
  periods,
  setPeriods,
  classGroups,
  // Patched in place when a section's class teacher changes, rather than
  // reloading every section for one field.
  setClassGroups,
  // Every SubjectRequirement in the school, owned by App.jsx (same
  // reasoning as subjects/teachers/periods/rooms above — this component
  // unmounts on every tab switch, so state kept locally here would be
  // destroyed right along with it). This section's own `requirements` is
  // just a filtered view of it, not separately fetched/cached, since
  // App.jsx already loads the whole list up front (TeachersSection needs
  // every section's data at once for its live workload total, so a lazy
  // per-visited-section cache — which is what this used to be — isn't an
  // option anymore anyway).
  allRequirements,
  setAllRequirements,
  onReloadSchoolData,
  readOnly = false,
  subView,
  onSubViewChange,
}) {
  const [activeSectionId, setActiveSectionId] = useState(classGroupId)
  const [error, setError] = useState(null)
  const [selectedSubjectIds, setSelectedSubjectIds] = useState([])
  // Elective blocks ticked in the same table, for copying with the subjects.
  const [selectedBlockIds, setSelectedBlockIds] = useState([])
  const [copyTargetIds, setCopyTargetIds] = useState([])
  const [copyPickerOpen, setCopyPickerOpen] = useState(false)
  const [copyingPeriods, setCopyingPeriods] = useState(false)
  const [settingUpPeriods, setSettingUpPeriods] = useState(false)

  const requirements = allRequirements.filter((r) => r.class_group_id === activeSectionId)
  // Elective blocks live in React Query rather than App.jsx's lifted state -
  // like rooms, they are newer than that arrangement.
  const { data: allElectiveBlocks = [] } = useElectiveBlocks(schoolId)
  const electiveBlocks = allElectiveBlocks.filter((b) => b.class_group_id === activeSectionId)
  const blockMutations = useElectiveBlockMutations(schoolId)

  // Full refresh — kept for the less-frequent call sites (bulk import,
  // quick period setup, a delete that could have cascaded into any
  // section's plan, or copying periods into other sections) where
  // re-fetching everything is the simplest correct thing to do and isn't
  // the hot path. `onReloadSchoolData` (App.jsx's loadSchoolData) already
  // covers allRequirements along with subjects/teachers/periods/rooms/
  // classGroups in one call.
  async function load() {
    await onReloadSchoolData()
  }

  // Follow the sidebar's selection by default; overridden locally via
  // the Plan page's section switcher without affecting the sidebar.
  useEffect(() => {
    setActiveSectionId(classGroupId)
  }, [classGroupId])

  async function handleSetClassTeacher(teacherId) {
    try {
      const updated = await api.updateClassGroup(activeSectionId, { class_teacher_id: teacherId })
      setClassGroups?.((prev) => prev.map((cg) => (cg.id === updated.id ? updated : cg)))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleQuickSetupPeriods() {
    if (settingUpPeriods) return
    setSettingUpPeriods(true)
    try {
      // The same structure the Setup page starts from - Mon-Fri, 8 periods -
      // saved in one request rather than forty.
      await api.saveTimetableStructure(schoolId, DEFAULT_STRUCTURE)
      await reloadPeriods()
    } catch (err) {
      setError(err.message)
    } finally {
      setSettingUpPeriods(false)
    }
  }

  // Bulk import's resource dropdown still includes "Class groups" even on
  // the Subjects/Teachers pages (nothing removed, just re-defaulted — see
  // BulkImportPanel's docstring) — `load()` already covers class groups
  // too now, since `onReloadSchoolData` (App.jsx's loadSchoolData) fetches
  // classGroups/teachers/subjects/periods/rooms together in one function.
  const reloadAll = load

  // Handed to SubjectsSection as a small, stable interface so it doesn't
  // need to know about `api` or this component's reload strategy.
  const subjectsApi = {
    async create(data) {
      // Shows the new row immediately (before the server round trip
      // resolves) instead of waiting for it — the round trip itself
      // (network + remote Postgres) is what was making "+ Add subject"
      // feel like a 2-3 second freeze even after this was already
      // reduced to a single call. The temp row is marked `_pending` so
      // SubjectsSection can disable editing it (and TeachersSection can
      // exclude it from qualification pickers) until the real subject
      // with its real id comes back; on failure the temp row is removed
      // again and the error surfaces as usual.
      const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
      const optimistic = { ...data, id: tempId, required_room_type: null, credits: null, lab_batch_count: null, _pending: true }
      setSubjects((prev) => [...prev, optimistic])
      try {
        const created = await api.createSubject(data)
        setSubjects((prev) => prev.map((s) => (s.id === tempId ? created : s)))
        return created
      } catch (err) {
        setSubjects((prev) => prev.filter((s) => s.id !== tempId))
        throw err
      }
    },
    async update(id, data) {
      // Patched in place from the server's response instead of a full
      // reload (5 parallel GETs) — renaming a subject or changing its
      // room type/credits doesn't affect teachers/periods/rooms/
      // requirements, so there's nothing else here that could have gone
      // stale.
      const updated = await api.updateSubject(id, data)
      setSubjects((prev) => prev.map((s) => (s.id === id ? updated : s)))
    },
    async delete(id) {
      // Removed locally instead of a full reload (5 parallel GETs), same
      // reasoning as update above. This does leave a removed subject's id
      // lingering in any teacher's `qualified_subject_ids` in local state
      // until that teacher is next reloaded — harmless, since nothing
      // reads a qualification against a subject that's no longer in the
      // `subjects` list (TeachersSection/PlanSection both filter/map over
      // `subjects` first), and it self-heals on the next full load.
      await api.deleteSubject(id)
      setSubjects((prev) => prev.filter((s) => s.id !== id))
      // The server also took the subject out of every elective block it was
      // an option in, and removed any block that left empty.
      blockMutations.invalidate()
    },
    reload: reloadAll,
  }

  // Saving the week's structure can add, remove and renumber periods all at
  // once, so the list is re-read whole rather than patched.
  async function reloadPeriods() {
    setPeriods(await api.listPeriods(schoolId))
  }

  const grades = [...new Set(classGroups.map((cg) => cg.grade).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true }),
  )

  // Rooms are the first resource off App.jsx's lifted state: fetched and
  // cached by React Query here rather than arriving as props from a
  // ten-endpoint load, and mutations invalidate only the rooms key.
  const { data: rooms = [] } = useRooms(schoolId)
  const roomsApi = useRoomMutations(schoolId)

  const teachersApi = {
    async update(id, data) {
      // Same reasoning as subjectsApi.update above — assigning/removing
      // a qualified subject or editing a teacher's own fields doesn't
      // touch subjects/periods/rooms/requirements.
      const updated = await api.updateTeacher(id, data)
      setTeachers((prev) => prev.map((t) => (t.id === id ? updated : t)))
    },
    async delete(id) {
      // Full reload, same reasoning as subjectsApi.delete: cascades into
      // other sections' requirements (preferred_teacher_id).
      await api.deleteTeacher(id)
      await load()
      // Also cleared as any block option's preferred teacher, server-side.
      blockMutations.invalidate()
    },
    reload: reloadAll,
  }

  // Replaces this section's slice of `allRequirements` with a freshly
  // computed one, leaving every other section's entries untouched — used
  // by all three handlers below instead of `load()`, which would refetch
  // subjects/teachers/periods/rooms/classGroups school-wide for what's
  // only ever a single-section edit.
  function replaceSectionRequirements(next) {
    setAllRequirements((prev) => [
      ...prev.filter((r) => r.class_group_id !== activeSectionId),
      ...next,
    ])
  }

  async function handleUpdatePeriods(subjectId, periodsPerWeek) {
    try {
      // Re-fetch just this section instead of reading from React state to
      // close a race if this field is blurred twice in quick succession
      // (e.g. tabbing through fields) — see PeriodsPerWeekInput's
      // docstring below.
      const fresh = await api.listRequirements(activeSectionId)
      const existing = fresh.find((r) => r.subject_id === subjectId)
      if (existing) {
        if (periodsPerWeek <= 0) {
          await api.deleteRequirement(existing.id)
          replaceSectionRequirements(fresh.filter((r) => r.id !== existing.id))
        } else {
          const updated = await api.updateRequirement(existing.id, { periods_per_week: periodsPerWeek })
          replaceSectionRequirements(fresh.map((r) => (r.id === existing.id ? updated : r)))
        }
      } else if (periodsPerWeek > 0) {
        const created = await api.createRequirement(activeSectionId, {
          class_group_id: activeSectionId,
          subject_id: subjectId,
          periods_per_week: periodsPerWeek,
        })
        replaceSectionRequirements([...fresh, created])
      }
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSetPreferredTeacher(subjectId, teacherId) {
    try {
      // Unlike handleUpdatePeriods above, this skips the leading re-fetch
      // and trusts `allRequirements` directly — a <select>'s onChange is
      // one discrete event, not a text field a user can blur twice in
      // quick succession, so there's no analogous race to guard against.
      const requirement = requirements.find((r) => r.subject_id === subjectId)
      if (!requirement) return // picker is only shown once a requirement exists
      const updated = await api.updateRequirement(requirement.id, { preferred_teacher_id: teacherId })
      setAllRequirements((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSetAssistantTeacher(subjectId, teacherId) {
    try {
      // Same reasoning as handleSetPreferredTeacher above.
      const requirement = requirements.find((r) => r.subject_id === subjectId)
      if (!requirement) return
      const updated = await api.updateRequirement(requirement.id, { assistant_teacher_id: teacherId })
      setAllRequirements((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    } catch (err) {
      setError(err.message)
    }
  }

  // Adds or removes this subject from the active section's plan — the
  // subject picker's checkbox toggle. Adding creates a requirement row
  // with a placeholder periods_per_week (1) the admin then fills in for
  // real in the table; removing deletes the row outright, same as
  // setting periods/week back to 0 in the table already does (this is
  // just a more discoverable way to do the same thing, plus it's how a
  // subject gets added in the first place now — the table no longer
  // shows every school subject to type a number into).
  async function handleToggleSectionSubject(subjectId, shouldSelect) {
    try {
      if (shouldSelect) {
        const created = await api.createRequirement(activeSectionId, {
          class_group_id: activeSectionId,
          subject_id: subjectId,
          periods_per_week: 1,
        })
        setAllRequirements((prev) => [...prev, created])
      } else {
        const existing = requirements.find((r) => r.subject_id === subjectId)
        if (!existing) return
        await api.deleteRequirement(existing.id)
        setAllRequirements((prev) => prev.filter((r) => r.id !== existing.id))
      }
    } catch (err) {
      setError(err.message)
    }
  }

  // Excludes subjects still `_pending` (optimistically added, not yet
  // confirmed by the server — see subjectsApi.create above) — setting
  // periods/week or a preferred teacher here would target the subject's
  // temporary id instead of its real one.
  // Used below to also filter by grade — a teacher whose Teacher.
  // qualified_grades is non-empty should only show up as "qualified" for
  // sections in one of those grades (empty = no restriction, same as the
  // solver's own check in app/services/solver.py).
  const activeSectionGrade = classGroups.find((cg) => cg.id === activeSectionId)?.grade

  // Eligible for the Assistant Teacher column — a standalone flag
  // (Teacher.is_assistant_eligible, set in TeachersSection), not gated by
  // qualified_subject_ids/qualified_grades the way the main teacher
  // picker is. An assistant doesn't need to be independently qualified to
  // teach the subject solo.
  const assistantEligibleTeachers = teachers.filter((t) => t.is_assistant_eligible)

  // Only subjects this section has actually been given a requirement
  // row for — i.e. ones an admin picked via the subject picker below —
  // not every subject in the school. A school with 20 subjects but one
  // section (say, Kindergarten) that only needs 6 of them shouldn't show
  // the other 14 as rows to skip past every time this page opens.
  const sectionSubjects = subjects.filter(
    (s) => !s._pending && requirements.some((r) => r.subject_id === s.id)
  )

  const rows = sectionSubjects.map((subject) => {
    const requirement = requirements.find((r) => r.subject_id === subject.id)
    const qualifiedTeachers = teachers.filter(
      (t) =>
        t.qualified_subject_ids.includes(subject.id) &&
        (!(t.qualified_grades?.length) || !activeSectionGrade || t.qualified_grades.includes(activeSectionGrade))
    )
    const periodsPerWeek = requirement?.periods_per_week ?? 0
    return {
      subject,
      periodsPerWeek,
      qualifiedTeachers,
      preferredTeacherId: requirement?.preferred_teacher_id ?? null,
      assistantTeacherId: requirement?.assistant_teacher_id ?? null,
      valid: periodsPerWeek > 0 && qualifiedTeachers.length > 0,
    }
  })

  const otherSections = classGroups.filter((cg) => cg.id !== activeSectionId)

  async function handleCopyPeriodsToOtherSections(targetIds) {
    if (copyingPeriods) return
    // Nothing ticked = copy everything; otherwise exactly what's ticked,
    // subjects and elective blocks alike.
    const pickedBlocks = electiveBlocks.filter((b) => selectedBlockIds.includes(b.id))
    const anyTicked = selectedSubjectIds.length > 0 || pickedBlocks.length > 0
    const rowsToCopy = anyTicked
      ? rows.filter((row) => selectedSubjectIds.includes(row.subject.id))
      : rows.filter((row) => row.periodsPerWeek > 0)
    const blocksToCopy = anyTicked ? pickedBlocks : electiveBlocks
    if (rowsToCopy.length === 0 && blocksToCopy.length === 0) {
      setError('Nothing to copy: set some periods/week in this section first.')
      return
    }

    const targets = otherSections.filter((cg) => targetIds.includes(cg.id))
    if (targets.length === 0) {
      setError('Pick at least one section to copy to.')
      return
    }

    const parts = []
    if (rowsToCopy.length) parts.push(`${rowsToCopy.length} subject${rowsToCopy.length === 1 ? '' : 's'}`)
    if (blocksToCopy.length) parts.push(`${blocksToCopy.length} elective block${blocksToCopy.length === 1 ? '' : 's'}`)
    const ok = await confirmDialog({
      title: `Copy ${parts.join(' and ')}?`,
      message: `They'll be copied to ${targets.length} section${targets.length === 1 ? '' : 's'}: ${targets
        .map((cg) => (cg.grade ? `${cg.grade} - ${cg.name}` : cg.name))
        .join(', ')}.${
        blocksToCopy.length
          ? ` Elective blocks: ${blocksToCopy.map((b) => b.name).join(', ')} - a section that already has a block with the same name gets it updated.`
          : ''
      }`,
      confirmLabel: 'Copy',
    })
    if (!ok) return

    setCopyingPeriods(true)
    setError(null)
    try {
      // One request, done in one transaction on the server. Sending one
      // request per subject per section all at once (56 for 8 x 7) could run
      // the backend out of database connections and fail with a 500.
      const result = await api.copyRequirements(activeSectionId, {
        target_ids: targets.map((t) => t.id),
        subject_ids: rowsToCopy.map((row) => row.subject.id),
        include_blocks: blocksToCopy.length > 0,
        block_ids: blocksToCopy.map((b) => b.id),
      })
      await Promise.all([load(), blockMutations.invalidate()])
      if (result?.skipped?.length) {
        setError(`Copied, except: ${result.skipped.join('; ')}.`)
      }
      setCopyTargetIds([])
      setCopyPickerOpen(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setCopyingPeriods(false)
    }
  }

  const activeSection = classGroups.find((cg) => cg.id === activeSectionId)

  return (
    <div className="flex max-w-5xl flex-col gap-5">
      {periods.length === 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
          <p className="mb-2">
            No periods set up yet. The solver needs these before it can generate a
            timetable.
          </p>
          {!readOnly && (
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={handleQuickSetupPeriods}
                disabled={settingUpPeriods}
                className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-60"
              >
                {settingUpPeriods ? 'Setting up…' : 'Quick setup: Mon–Fri, 8 periods/day'}
              </button>
              {subView !== 'setup' && (
                <button
                  onClick={() => onSubViewChange('setup')}
                  className="text-xs font-medium text-amber-800 underline underline-offset-2"
                >
                  or set custom period timings in Setup
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Subjects / Teachers / Setup are steps in the header (App.jsx
          BASE_TABS), so the page doesn't repeat them as tabs of its own. */}
      {subView === 'plan' && (
        <button
          onClick={() => onSubViewChange('subjects')}
          className="w-fit text-xs font-medium text-neutral-900 hover:underline"
        >
          ← Manage school subjects &amp; teachers
        </button>
      )}

      {subView === 'subjects' && (
        <SubjectsSection
          schoolId={schoolId}
          subjects={subjects}
          onSubjectsChanged={subjectsApi}
          institutionType={institutionType}
          readOnly={readOnly}
        />
      )}

      {subView === 'teachers' && (
        <TeachersSection
          schoolId={schoolId}
          teachers={teachers}
          subjects={subjects}
          classGroups={classGroups}
          allRequirements={allRequirements}
          onTeachersChanged={teachersApi}
          readOnly={readOnly}
        />
      )}

      {subView === 'setup' && (
        <SetupSection
          schoolId={schoolId}
          periods={periods}
          grades={grades}
          onPeriodsSaved={reloadPeriods}
          rooms={rooms}
          onRoomsChanged={roomsApi}
          onImported={load}
          readOnly={readOnly}
        />
      )}

      {subView === 'plan' && (
        <PlanSection
          rows={rows}
          subjects={subjects}
          onToggleSectionSubject={handleToggleSectionSubject}
          classGroups={classGroups}
          otherSections={otherSections}
          activeSectionId={activeSectionId}
          activeSection={activeSection}
          onActiveSectionChange={setActiveSectionId}
          onUpdatePeriods={handleUpdatePeriods}
          onSetPreferredTeacher={handleSetPreferredTeacher}
          assistantEligibleTeachers={assistantEligibleTeachers}
          onSetAssistantTeacher={handleSetAssistantTeacher}
          selectedSubjectIds={selectedSubjectIds}
          onSelectedSubjectIdsChange={setSelectedSubjectIds}
          selectedBlockIds={selectedBlockIds}
          onSelectedBlockIdsChange={setSelectedBlockIds}
          copyTargetIds={copyTargetIds}
          onCopyTargetIdsChange={setCopyTargetIds}
          copyPickerOpen={copyPickerOpen}
          onCopyPickerOpenChange={setCopyPickerOpen}
          onCopyToOtherSections={handleCopyPeriodsToOtherSections}
          copyingPeriods={copyingPeriods}
          onGoToSubjects={() => onSubViewChange('subjects')}
          electiveBlocks={electiveBlocks}
          classTeacherPicker={
            activeSection && (
              <ClassTeacherPicker
                section={activeSection}
                teachers={teachers}
                classGroups={classGroups}
                onChange={handleSetClassTeacher}
                readOnly={readOnly}
              />
            )
          }
          electiveBlocksPanel={
            activeSectionId != null && (
              <ElectiveBlocksPanel
                schoolId={schoolId}
                classGroupId={activeSectionId}
                sectionGrade={activeSectionGrade}
                blocks={electiveBlocks}
                commonSubjectIds={requirements.map((r) => r.subject_id)}
                subjects={subjects}
                teachers={teachers}
                mutations={blockMutations}
                readOnly={readOnly}
              />
            )
          }
          readOnly={readOnly}
        />
      )}
    </div>
  )
}

/**
 * Periods and rooms — the school's foundational, one-time setup. Used to
 * live as a collapsed "Setup — manage" text-link disclosure sitting above
 * the Subjects/Teachers sub-nav, which made it easy for a new admin to
 * never notice it was there at all. It's a full sub-page now, a peer of
 * Subjects and Teachers, since it's exactly as much "a point of data
 * entry" as those two — a school can't get a working timetable without
 * its periods and rooms configured.
 */
function SetupSection({ schoolId, periods, grades, onPeriodsSaved, rooms, onRoomsChanged, onImported, readOnly }) {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h4 className="text-base font-medium">Setup</h4>
        <p className="mt-1 text-sm text-slate-500">
          Your school's daily schedule (periods) and physical rooms. Configure these once, then
          add subjects and teachers.
        </p>
      </div>

      <div className="divide-y divide-slate-200 rounded-md border border-slate-200">
        <div className="p-4">
          <h5 className="mb-3 text-sm font-medium text-slate-700">
            Timetable structure{' '}
            {periods.length > 0 && <span className="text-slate-400">({periods.length} periods a week)</span>}
          </h5>
          <TimetableStructurePanel
            schoolId={schoolId}
            grades={grades}
            onSaved={onPeriodsSaved}
            readOnly={readOnly}
          />
        </div>
        <div className="p-4">
          <h5 className="mb-3 text-sm font-medium text-slate-700">
            Rooms {rooms.length > 0 && <span className="text-slate-400">({rooms.length})</span>}
          </h5>
          <RoomsPanel
            schoolId={schoolId}
            rooms={rooms}
            onCreate={onRoomsChanged.create}
            onDelete={onRoomsChanged.delete}
            readOnly={readOnly}
          />
        </div>
        {!readOnly && (
          <div className="p-4">
            <BulkImportPanel schoolId={schoolId} resource="rooms" onImported={onImported} />
          </div>
        )}
        {!readOnly && (
          <div className="p-4">
            <SetupExtractionPanel schoolId={schoolId} onImported={onImported} />
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * "How many periods/week does the currently selected section need of
 * each subject" plus which teacher covers it here — the one genuinely
 * per-section question in Data Entry. Everything else (subject list,
 * teacher list/qualifications) lives on the other two sub-pages; this
 * one only reads them.
 */
function PlanSection({
  rows,
  subjects,
  onToggleSectionSubject,
  classGroups,
  otherSections,
  activeSectionId,
  activeSection,
  onActiveSectionChange,
  onUpdatePeriods,
  onSetPreferredTeacher,
  assistantEligibleTeachers,
  onSetAssistantTeacher,
  selectedSubjectIds,
  onSelectedSubjectIdsChange,
  selectedBlockIds = [],
  onSelectedBlockIdsChange = () => {},
  copyTargetIds,
  onCopyTargetIdsChange,
  copyPickerOpen,
  onCopyPickerOpenChange,
  onCopyToOtherSections,
  copyingPeriods,
  onGoToSubjects,
  electiveBlocks = [],
  classTeacherPicker = null,
  electiveBlocksPanel = null,
  readOnly,
}) {
  // Whether the subject picker (below) is showing instead of the periods/
  // week table. Starts open for a section with nothing picked yet, closed
  // otherwise — decided once per section switch (the effect below), not
  // re-derived from `rows.length` on every render, which is what this
  // used to do: as soon as the *first* checked subject's create request
  // resolved, `rows.length` flipped from 0 to 1 and the whole picker
  // vanished into the table mid-selection, cutting the admin off if they
  // meant to pick several subjects before continuing. Now it only closes
  // when "Continue"/"Edit subjects" explicitly say so.
  const [subjectPickerOpen, setSubjectPickerOpen] = useState(() => rows.length === 0)
  useEffect(() => {
    setSubjectPickerOpen(rows.length === 0)
    // Deliberately only re-derives on a section switch, not whenever
    // `rows` changes — see the comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSectionId])
  // Optimistic override for the picker's checkboxes — without this, each
  // click waited on a full round trip (through Railway, then Supabase)
  // before visually checking/unchecking at all, since `rows` only reflects
  // what the server has confirmed. On a slow connection that reads as
  // unresponsive, and clicking several boxes in a row before the first
  // request resolves computes each one from the same stale pre-click
  // state (same race already fixed for the sidebar's grade reorder).
  // Cleared once the server-confirmed selection actually matches what was
  // optimistically set, so `rows` becomes the source of truth again as
  // soon as it can be.
  const [localSelectedSubjectIds, setLocalSelectedSubjectIds] = useState(null)
  const confirmedSelectedSubjectIds = rows.map((row) => row.subject.id)
  const confirmedSelectedKey = [...confirmedSelectedSubjectIds].sort((a, b) => a - b).join(',')
  useEffect(() => {
    if (
      localSelectedSubjectIds &&
      [...localSelectedSubjectIds].sort((a, b) => a - b).join(',') === confirmedSelectedKey
    ) {
      setLocalSelectedSubjectIds(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmedSelectedKey])
  const pickerSelectedSubjectIds = localSelectedSubjectIds ?? confirmedSelectedSubjectIds

  function handlePickerToggle(subjectId, shouldSelect) {
    setLocalSelectedSubjectIds(
      shouldSelect ? [...pickerSelectedSubjectIds, subjectId] : pickerSelectedSubjectIds.filter((id) => id !== subjectId)
    )
    onToggleSectionSubject(subjectId, shouldSelect)
  }

  // A block counts once: its options all run in the same periods, so a
  // six-period block is six periods of the section's week, not six per option.
  const totalWeeklyPeriods =
    rows.reduce((sum, row) => sum + row.periodsPerWeek, 0) +
    electiveBlocks.reduce((sum, b) => sum + b.periods_per_week, 0)
  // Which block, if any, each subject is already an option in. Such a subject
  // can't also be one everybody takes - the server refuses it - so the picker
  // says where it is instead of offering it.
  const blockOfSubject = new Map(
    electiveBlocks.flatMap((b) => b.options.map((o) => [o.subject_id, b.name])),
  )
  // Ticked blocks still in this section (a stale id from another section
  // doesn't count).
  const tickedBlockIds = selectedBlockIds.filter((id) => electiveBlocks.some((b) => b.id === id))
  const itemCount = rows.length + electiveBlocks.length
  const selectedAll =
    itemCount > 0 && selectedSubjectIds.length === rows.length && tickedBlockIds.length === electiveBlocks.length
  const selectedCount = selectedSubjectIds.length
  const anyTicked = selectedCount > 0 || tickedBlockIds.length > 0
  const subjectName = (id) => subjects.find((x) => x.id === id)?.name ?? 'Unknown subject'

  function toggleSelectedBlock(blockId) {
    onSelectedBlockIdsChange(
      tickedBlockIds.includes(blockId) ? tickedBlockIds.filter((id) => id !== blockId) : [...tickedBlockIds, blockId],
    )
  }

  function toggleSelectedSubject(subjectId) {
    onSelectedSubjectIdsChange(
      selectedSubjectIds.includes(subjectId)
        ? selectedSubjectIds.filter((id) => id !== subjectId)
        : [...selectedSubjectIds, subjectId]
    )
  }

  function toggleSelectAll() {
    onSelectedSubjectIdsChange(selectedAll ? [] : rows.map((row) => row.subject.id))
    onSelectedBlockIdsChange(selectedAll ? [] : electiveBlocks.map((b) => b.id))
  }

  if (classGroups.length === 0) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
        <p>
          No grades/sections yet. Use "+ Add" in the sidebar to create one, then come back here
          to plan periods/week per subject.
        </p>
      </div>
    )
  }

  const availableSubjects = subjects.filter((s) => !s._pending)

  if (availableSubjects.length === 0) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
        <p className="mb-2">No subjects yet. Add some on the Subjects page first.</p>
        <button
          onClick={onGoToSubjects}
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700"
        >
          Go to Subjects
        </button>
      </div>
    )
  }

  // Shown instead of the periods/week table either the first time this
  // section has no subjects picked yet, or when "Edit subjects" below
  // reopens it on purpose.
  if (subjectPickerOpen) {
    return (
      <div className="flex flex-col gap-5">
        <div>
          <h4 className="text-base font-medium">This section's plan</h4>
          <p className="mt-1 text-sm text-slate-500">
            {pickerSelectedSubjectIds.length === 0
              ? "First, pick which subjects this section needs. Only these show up below, not every subject in the school."
              : 'Add or remove subjects for this section.'}
          </p>
        </div>
        <SectionSubjectPicker
          subjects={availableSubjects}
          selectedSubjectIds={pickerSelectedSubjectIds}
          onToggleSubject={handlePickerToggle}
          blockOfSubject={blockOfSubject}
          onDone={() => setSubjectPickerOpen(false)}
          canFinish={pickerSelectedSubjectIds.length > 0}
          readOnly={readOnly}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-base font-medium">This section's plan</h4>
          <p className="mt-1 text-sm text-slate-500">
            How many periods/week this section needs of each subject, and who teaches it here.
          </p>
        </div>
        {!readOnly && (
          <button
            onClick={() => setSubjectPickerOpen(true)}
            className="flex-none rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Edit subjects
          </button>
        )}
      </div>

      <div className="rounded-md border border-neutral-200 bg-neutral-100/60 p-4 text-sm text-slate-600">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-1.5">
            <strong>{totalWeeklyPeriods}</strong> total periods/week for
            {classGroups.length > 1 ? (
              <>
                <label htmlFor="active-section-select" className="sr-only">Section</label>
                <select
                  id="active-section-select"
                  value={activeSectionId ?? ''}
                  onChange={(e) => onActiveSectionChange(Number(e.target.value))}
                  className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm font-medium text-neutral-700 focus:border-neutral-900 focus:outline-none"
                >
                  {classGroups.map((cg) => (
                    <option key={cg.id} value={cg.id}>
                      {cg.grade ? `${cg.grade} · ` : ''}Section {cg.name}
                    </option>
                  ))}
                </select>
              </>
            ) : (
              <span className="font-medium">
                {activeSection ? (activeSection.grade ? `${activeSection.grade} · ` : '') + `Section ${activeSection.name}` : 'this section'}
              </span>
            )}
          </div>
          {!readOnly && (
            <div className="relative flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={toggleSelectAll}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-100"
              >
                {selectedAll ? 'Clear selection' : `Select all ${itemCount}`}
              </button>
              <button
                type="button"
                onClick={() => onCopyPickerOpenChange(!copyPickerOpen)}
                disabled={copyingPeriods || otherSections.length === 0}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
              >
                {copyingPeriods ? 'Copying…' : copyButtonLabel(
                  anyTicked ? selectedCount : rows.filter((row) => row.periodsPerWeek > 0).length,
                  anyTicked ? tickedBlockIds.length : electiveBlocks.length,
                )}
              </button>
              {copyPickerOpen && (
                <CopyTargetPicker
                  otherSections={otherSections}
                  copyTargetIds={copyTargetIds}
                  onCopyTargetIdsChange={onCopyTargetIdsChange}
                  onCancel={() => onCopyPickerOpenChange(false)}
                  onConfirm={() => onCopyToOtherSections(copyTargetIds)}
                  copying={copyingPeriods}
                />
              )}
            </div>
          )}
        </div>
      </div>

      {classTeacherPicker}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-500">
            <th className="w-10 py-2 font-medium">
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={selectedAll}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-slate-300 text-slate-900"
                />
                <span className="sr-only">Select all</span>
              </label>
            </th>
            <th className="w-1/3 py-2 font-medium">Subject</th>
            <th className="w-32 py-2 font-medium">Periods/week</th>
            <th className="py-2 font-medium">Teacher</th>
            <th className="py-2 font-medium">Assistant teacher</th>
            <th className="w-28 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ subject, periodsPerWeek, qualifiedTeachers, preferredTeacherId, assistantTeacherId, valid }) => (
            <tr key={subject.id} className="border-b border-slate-100">
              <td className="py-2 pr-2 align-top">
                <input
                  type="checkbox"
                  checked={selectedSubjectIds.includes(subject.id)}
                  onChange={() => toggleSelectedSubject(subject.id)}
                  className="h-4 w-4 rounded border-slate-300 text-slate-900"
                />
              </td>
              <td className="py-2 pr-2">{subject.name}</td>
              <td className="py-2 pr-2">
                <PeriodsPerWeekInput
                  value={periodsPerWeek}
                  onSave={(val) => onUpdatePeriods(subject.id, val)}
                  disabled={readOnly}
                />
              </td>
              <td className="py-2 pr-2">
                {qualifiedTeachers.length === 0 ? (
                  <span className="text-xs text-slate-400">No qualified teacher yet</span>
                ) : qualifiedTeachers.length === 1 ? (
                  <span className="text-sm text-slate-600">{qualifiedTeachers[0].name}</span>
                ) : (
                  <select
                    value={preferredTeacherId ?? ''}
                    disabled={readOnly || periodsPerWeek <= 0}
                    onChange={(e) =>
                      onSetPreferredTeacher(subject.id, e.target.value ? Number(e.target.value) : null)
                    }
                    title="Which teacher covers this section. Pinning one speeds up generation for large schools"
                    className="rounded border border-neutral-200 bg-neutral-100/40 px-1.5 py-1 text-xs text-neutral-700 hover:bg-neutral-100"
                  >
                    <option value="">Any (let solver choose)</option>
                    {qualifiedTeachers.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                )}
              </td>
              <td className="py-2 pr-2">
                {assistantEligibleTeachers.length === 0 ? (
                  <span className="text-xs text-slate-400">No eligible teachers</span>
                ) : (
                  <select
                    value={assistantTeacherId ?? ''}
                    disabled={readOnly || periodsPerWeek <= 0}
                    onChange={(e) =>
                      onSetAssistantTeacher(subject.id, e.target.value ? Number(e.target.value) : null)
                    }
                    title="An optional second teacher for this subject in this section. Mark a teacher 'eligible as an assistant teacher' on the Teachers page to add them here"
                    className="rounded border border-slate-200 bg-slate-50 px-1.5 py-1 text-xs text-slate-600 hover:bg-slate-100"
                  >
                    <option value="">None</option>
                    {assistantEligibleTeachers.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                )}
              </td>
              <td className="py-2 pr-2">
                {valid ? (
                  <span className="text-xs font-medium text-emerald-700">✓ Ready</span>
                ) : periodsPerWeek <= 0 ? (
                  <span className="text-xs text-slate-500">Set periods/week</span>
                ) : (
                  <span className="text-xs text-slate-500">Needs a teacher</span>
                )}
              </td>
            </tr>
          ))}
          {/* Elective blocks: one row each, ticked and copied like a subject.
              Their options and teachers are edited in the panel below. */}
          {electiveBlocks.map((block) => (
            <tr key={`block-${block.id}`} className="border-b border-slate-100 bg-violet-50/40">
              <td className="py-2 pr-2 align-top">
                <input
                  type="checkbox"
                  aria-label={`Select ${block.name}`}
                  checked={tickedBlockIds.includes(block.id)}
                  onChange={() => toggleSelectedBlock(block.id)}
                  className="h-4 w-4 rounded border-slate-300 text-slate-900"
                />
              </td>
              <td className="py-2 pr-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-slate-800">{block.name}</span>
                  <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-800">
                    Elective block
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {block.options.map((o) => subjectName(o.subject_id)).join(' / ')}
                </div>
              </td>
              <td className="py-2 pr-2 pl-3 text-slate-700">{block.periods_per_week}</td>
              <td className="py-2 pr-2 text-xs text-slate-500" colSpan={2}>
                {block.options.length} options at the same time, each with its own teacher
              </td>
              <td className="py-2 pr-2 text-xs text-slate-500">Edit below</td>
            </tr>
          ))}
          <tr className="bg-slate-50 text-slate-600">
            <td className="py-3 pr-2"></td>
            <td className="py-3 pr-2 text-sm font-semibold">Total</td>
            <td className="py-3 pr-2 font-semibold">{totalWeeklyPeriods}</td>
            <td colSpan={3} className="py-3 text-sm text-slate-500">
              Total periods/week configured for the section selected above
              {electiveBlocks.length > 0 && ', including its elective blocks'}.
            </td>
          </tr>
        </tbody>
      </table>

      {electiveBlocksPanel}
    </div>
  )
}

// "Copy 9 subjects + 1 block to…" - the blocks go along with the subjects.
function copyButtonLabel(subjectCount, blockCount) {
  const parts = []
  if (subjectCount > 0 || blockCount === 0) parts.push(`${subjectCount} subject${subjectCount === 1 ? '' : 's'}`)
  if (blockCount > 0) parts.push(`${blockCount} block${blockCount === 1 ? '' : 's'}`)
  return `Copy ${parts.join(' + ')} to…`
}

/**
 * Who this section's class teacher is - the teacher with them in the class
 * teacher period. One per section; a teacher who is class teacher of two
 * sections can't be in both at once, so that is pointed out rather than
 * refused (it is sometimes a stopgap while someone is away).
 */
function ClassTeacherPicker({ section, teachers, classGroups, onChange, readOnly }) {
  const others = classGroups.filter(
    (cg) => cg.id !== section.id && section.class_teacher_id != null && cg.class_teacher_id === section.class_teacher_id,
  )
  const teacherName = teachers.find((t) => t.id === section.class_teacher_id)?.name
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label htmlFor="class-teacher-select" className="font-medium text-slate-700">
        Class teacher
      </label>
      <select
        id="class-teacher-select"
        value={section.class_teacher_id ?? ''}
        disabled={readOnly}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
      >
        <option value="">Not set</option>
        {[...teachers]
          .filter((t) => !t._pending)
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
      </select>
      {others.length > 0 && (
        <span className="text-xs text-amber-700">
          {teacherName} is also class teacher of{' '}
          {others.map((cg) => (cg.grade ? `${cg.grade} · ${cg.name}` : cg.name)).join(', ')} - they can only be
          in one class teacher period at a time.
        </span>
      )}
    </div>
  )
}

/**
 * Checkbox list of the school's subjects for picking which ones apply to
 * one section — shown full-page the first time a section has none picked
 * yet, and re-openable afterward via "Edit subjects" in PlanSection to
 * add/remove. Checking a box creates that subject's requirement row
 * (periods_per_week starts at a placeholder 1, filled in for real in the
 * table); unchecking deletes it — same underlying operation as setting
 * periods/week back to 0 in the table, just a more discoverable way in.
 */
function SectionSubjectPicker({
  subjects,
  selectedSubjectIds,
  onToggleSubject,
  onDone,
  canFinish,
  readOnly,
  blockOfSubject = new Map(),
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 md:grid-cols-3">
        {subjects.map((s) => {
          const inBlock = blockOfSubject.get(s.id)
          return (
            <label
              key={s.id}
              title={inBlock ? `An option in ${inBlock}. Edit the block to change it` : undefined}
              className={`flex items-center gap-2 rounded px-2 py-1.5 text-sm ${
                inBlock ? 'cursor-not-allowed text-slate-400' : 'cursor-pointer hover:bg-slate-50'
              }`}
            >
              <input
                type="checkbox"
                checked={selectedSubjectIds.includes(s.id)}
                disabled={readOnly || !!inBlock}
                onChange={(e) => onToggleSubject(s.id, e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-slate-900"
              />
              {s.name}
              {inBlock && <span className="text-xs">({inBlock})</span>}
            </label>
          )
        })}
      </div>
      {canFinish && (
        <div className="mt-4 flex justify-end border-t border-slate-100 pt-3">
          <button
            onClick={onDone}
            className="rounded-md bg-neutral-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-neutral-700"
          >
            Continue to periods/week →
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * Small dropdown-style panel for picking which sections a "copy periods"
 * action should apply to, instead of silently always copying to every
 * other section in the school — a school with several unrelated grades
 * (say, 6 and 11) has no reason to want grade 6's subject plan pushed
 * into grade 11 just because they're both "other sections."
 */
function CopyTargetPicker({ otherSections, copyTargetIds, onCopyTargetIdsChange, onCancel, onConfirm, copying }) {
  const allSelected = copyTargetIds.length === otherSections.length && otherSections.length > 0

  function toggleTarget(id) {
    onCopyTargetIdsChange(
      copyTargetIds.includes(id) ? copyTargetIds.filter((x) => x !== id) : [...copyTargetIds, id]
    )
  }

  function toggleAll() {
    onCopyTargetIdsChange(allSelected ? [] : otherSections.map((cg) => cg.id))
  }

  return (
    <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-md border border-slate-200 bg-white p-3 shadow-lg">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500">Copy to which sections?</span>
        <button type="button" onClick={toggleAll} className="text-xs font-medium text-neutral-900 hover:underline">
          {allSelected ? 'Clear' : 'Select all'}
        </button>
      </div>
      <div className="mt-2 max-h-48 overflow-y-auto">
        {otherSections.map((cg) => (
          <label key={cg.id} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-slate-50">
            <input
              type="checkbox"
              checked={copyTargetIds.includes(cg.id)}
              onChange={() => toggleTarget(cg.id)}
            />
            {cg.grade ? `${cg.grade} · ` : ''}Section {cg.name}
          </label>
        ))}
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="text-xs font-medium text-slate-500 hover:text-slate-700">
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={copying || copyTargetIds.length === 0}
          className="rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
        >
          {copying ? 'Copying…' : `Copy to ${copyTargetIds.length || ''} section${copyTargetIds.length === 1 ? '' : 's'}`}
        </button>
      </div>
    </div>
  )
}

/**
 * A controlled periods/week field, explicitly re-synced to `value`
 * whenever it changes (e.g. switching sections).
 *
 * The previous version used an uncontrolled input (`defaultValue`), which
 * only sets the DOM's value on first mount — React does not update it on
 * later re-renders. Since this row's <tr> was reused across section
 * switches (same subject.id, so same React key), the box kept showing
 * whichever section's number it happened to mount with first, even after
 * the real underlying value changed. That's exactly the "Section B shows
 * Section A's periods" bug. A controlled input with this effect can't
 * drift from the real value, regardless of how the parent re-renders.
 */
function PeriodsPerWeekInput({ value, onSave, disabled = false }) {
  const [text, setText] = useState(String(value))

  useEffect(() => {
    setText(String(value))
  }, [value])

  function handleBlur() {
    const val = Number(text) || 0
    if (val !== value) onSave(val)
    else setText(String(value)) // normalize e.g. "007" -> "7"
  }

  return (
    <input
      type="number"
      min="0"
      value={text}
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={handleBlur}
      className="w-16 rounded px-1.5 py-1 text-sm hover:bg-slate-50 focus:bg-slate-50 focus:outline-none disabled:bg-transparent disabled:text-slate-700"
    />
  )
}
