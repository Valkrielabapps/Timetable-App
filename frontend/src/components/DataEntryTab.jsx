import { useEffect, useState } from 'react'
import { api } from '../api'
import BulkImportPanel from './BulkImportPanel'
import PeriodsPanel from './PeriodsPanel'
import RoomsPanel from './RoomsPanel'
import SetupExtractionPanel from './SetupExtractionPanel'
import SubjectsSection from './SubjectsSection'
import TeachersSection from './TeachersSection'

const SUB_VIEWS = [
  { id: 'subjects', label: 'Subjects' },
  { id: 'teachers', label: 'Teachers' },
  { id: 'setup', label: 'Setup' },
]

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
  rooms,
  setRooms,
  classGroups,
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
  const [copyTargetIds, setCopyTargetIds] = useState([])
  const [copyPickerOpen, setCopyPickerOpen] = useState(false)
  const [copyingPeriods, setCopyingPeriods] = useState(false)
  const [settingUpPeriods, setSettingUpPeriods] = useState(false)

  const requirements = allRequirements.filter((r) => r.class_group_id === activeSectionId)

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

  async function handleQuickSetupPeriods() {
    if (settingUpPeriods) return
    setSettingUpPeriods(true)
    try {
      const calls = []
      for (let day = 0; day < 5; day++) {
        for (let order = 0; order < 8; order++) {
          calls.push(
            api.createPeriod({
              school_id: schoolId,
              day_of_week: day,
              order,
              label: `Period ${order + 1}`,
            })
          )
        }
      }
      await Promise.all(calls)
      await load()
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
    },
    reload: reloadAll,
  }

  // Handed to PeriodsPanel/RoomsPanel (via SetupSection) so they read/write
  // App.jsx's lifted `periods`/`rooms` state directly instead of each
  // independently re-fetching its own list on mount — see PeriodsPanel's
  // and RoomsPanel's docstrings for why that round trip was the visible
  // lag on opening Setup.
  const periodsApi = {
    async create(data) {
      const created = await api.createPeriod(data)
      setPeriods((prev) => [...prev, created])
      return created
    },
    async update(id, data) {
      const updated = await api.updatePeriod(id, data)
      setPeriods((prev) => prev.map((p) => (p.id === id ? updated : p)))
      return updated
    },
    async delete(id) {
      await api.deletePeriod(id)
      setPeriods((prev) => prev.filter((p) => p.id !== id))
    },
  }

  const roomsApi = {
    async create(data) {
      const created = await api.createRoom(data)
      setRooms((prev) => [...prev, created])
      return created
    },
    async delete(id) {
      await api.deleteRoom(id)
      setRooms((prev) => prev.filter((r) => r.id !== id))
    },
  }

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
    const rowsToCopy = selectedSubjectIds.length > 0
      ? rows.filter((row) => selectedSubjectIds.includes(row.subject.id))
      : rows.filter((row) => row.periodsPerWeek > 0)
    if (rowsToCopy.length === 0) {
      setError('Nothing to copy: set some periods/week in this section first.')
      return
    }

    const targets = otherSections.filter((cg) => targetIds.includes(cg.id))
    if (targets.length === 0) {
      setError('Pick at least one section to copy to.')
      return
    }

    if (!window.confirm(`Copy ${rowsToCopy.length} subject assignment${rowsToCopy.length === 1 ? '' : 's'} to ${targets.length} section${targets.length === 1 ? '' : 's'}?`)) {
      return
    }

    setCopyingPeriods(true)
    setError(null)
    try {
      const calls = []
      for (const target of targets) {
        for (const row of rowsToCopy) {
          calls.push(
            api.createRequirement(target.id, {
              class_group_id: target.id,
              subject_id: row.subject.id,
              periods_per_week: row.periodsPerWeek,
            })
          )
        }
      }
      await Promise.all(calls)
      await load()
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
            No periods set up yet — the solver needs these before it can generate a
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

      {subView === 'plan' ? (
        <button
          onClick={() => onSubViewChange('subjects')}
          className="w-fit text-xs font-medium text-neutral-900 hover:underline"
        >
          ← Manage school subjects &amp; teachers
        </button>
      ) : (
        <nav className="flex gap-1 border-b border-slate-200 text-sm">
          {SUB_VIEWS.map((v) => {
            const count =
              v.id === 'subjects' ? subjects.length : v.id === 'teachers' ? teachers.length : periods.length
            return (
              <button
                key={v.id}
                onClick={() => onSubViewChange(v.id)}
                className={`-mb-px border-b-2 px-3 py-2 font-medium ${
                  subView === v.id
                    ? 'border-neutral-900 text-neutral-700'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {v.label}
                <span className="ml-1 text-xs text-slate-400">({count})</span>
              </button>
            )
          })}
        </nav>
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
          onPeriodsChanged={periodsApi}
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
          copyTargetIds={copyTargetIds}
          onCopyTargetIdsChange={setCopyTargetIds}
          copyPickerOpen={copyPickerOpen}
          onCopyPickerOpenChange={setCopyPickerOpen}
          onCopyToOtherSections={handleCopyPeriodsToOtherSections}
          copyingPeriods={copyingPeriods}
          onGoToSubjects={() => onSubViewChange('subjects')}
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
function SetupSection({ schoolId, periods, onPeriodsChanged, rooms, onRoomsChanged, onImported, readOnly }) {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h4 className="text-base font-medium">Setup</h4>
        <p className="mt-1 text-sm text-slate-500">
          Your school's daily schedule (periods) and physical rooms — configure these once, then
          add subjects and teachers.
        </p>
      </div>

      <div className="divide-y divide-slate-200 rounded-md border border-slate-200">
        <div className="p-4">
          <h5 className="mb-3 text-sm font-medium text-slate-700">
            Periods {periods.length > 0 && <span className="text-slate-400">({periods.length})</span>}
          </h5>
          <PeriodsPanel
            schoolId={schoolId}
            periods={periods}
            onCreate={onPeriodsChanged.create}
            onUpdate={onPeriodsChanged.update}
            onDelete={onPeriodsChanged.delete}
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
  copyTargetIds,
  onCopyTargetIdsChange,
  copyPickerOpen,
  onCopyPickerOpenChange,
  onCopyToOtherSections,
  copyingPeriods,
  onGoToSubjects,
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

  const totalWeeklyPeriods = rows.reduce((sum, row) => sum + row.periodsPerWeek, 0)
  const selectedAll = selectedSubjectIds.length === rows.length && rows.length > 0
  const selectedCount = selectedSubjectIds.length

  function toggleSelectedSubject(subjectId) {
    onSelectedSubjectIdsChange(
      selectedSubjectIds.includes(subjectId)
        ? selectedSubjectIds.filter((id) => id !== subjectId)
        : [...selectedSubjectIds, subjectId]
    )
  }

  function toggleSelectAll() {
    onSelectedSubjectIdsChange(selectedAll ? [] : rows.map((row) => row.subject.id))
  }

  if (classGroups.length === 0) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
        <p>
          No grades/sections yet — use "+ Add" in the sidebar to create one, then come back here
          to plan periods/week per subject.
        </p>
      </div>
    )
  }

  const availableSubjects = subjects.filter((s) => !s._pending)

  if (availableSubjects.length === 0) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
        <p className="mb-2">No subjects yet — add some on the Subjects page first.</p>
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
              ? "First, pick which subjects this section needs — only these show up below, not every subject in the school."
              : 'Add or remove subjects for this section.'}
          </p>
        </div>
        <SectionSubjectPicker
          subjects={availableSubjects}
          selectedSubjectIds={pickerSelectedSubjectIds}
          onToggleSubject={handlePickerToggle}
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
                {selectedAll ? 'Clear selection' : `Select ${rows.length} subject${rows.length === 1 ? '' : 's'}`}
              </button>
              <button
                type="button"
                onClick={() => onCopyPickerOpenChange(!copyPickerOpen)}
                disabled={copyingPeriods || otherSections.length === 0}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
              >
                {copyingPeriods
                  ? 'Copying…'
                  : `Copy ${selectedCount > 0 ? selectedCount : rows.filter((row) => row.periodsPerWeek > 0).length} subject${(selectedCount > 0 ? selectedCount : rows.filter((row) => row.periodsPerWeek > 0).length) === 1 ? '' : 's'} to…`}
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
                    title="Which teacher covers this section — pinning one speeds up generation for large schools"
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
                    title="An optional second teacher for this subject in this section — mark a teacher 'eligible as an assistant teacher' on the Teachers page to add them here"
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
          <tr className="bg-slate-50 text-slate-600">
            <td className="py-3 pr-2"></td>
            <td className="py-3 pr-2 text-sm font-semibold">Total</td>
            <td className="py-3 pr-2 font-semibold">{totalWeeklyPeriods}</td>
            <td colSpan={3} className="py-3 text-sm text-slate-500">
              Total periods/week configured for the section selected above.
            </td>
          </tr>
        </tbody>
      </table>
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
function SectionSubjectPicker({ subjects, selectedSubjectIds, onToggleSubject, onDone, canFinish, readOnly }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 md:grid-cols-3">
        {subjects.map((s) => (
          <label
            key={s.id}
            className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50"
          >
            <input
              type="checkbox"
              checked={selectedSubjectIds.includes(s.id)}
              disabled={readOnly}
              onChange={(e) => onToggleSubject(s.id, e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-slate-900"
            />
            {s.name}
          </label>
        ))}
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
