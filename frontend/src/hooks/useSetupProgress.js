/**
 * The six-step journey from a brand-new section to a generated timetable
 * (periods -> subjects -> teachers -> this section's plan -> constraints
 * (optional) -> generate), as real counts read from App.jsx's own live
 * state. Used by both the always-visible header progress bar (App.jsx)
 * and the detailed step list (OverviewTab.jsx) so the two can never drift
 * apart — before this, OverviewTab computed its own steps locally and the
 * header had no equivalent at all, meaning progress was invisible on
 * every tab except Overview, which is where a new admin spends the least
 * time (the actual setup work happens on Data Entry and Constraints).
 *
 * Subjects and teachers are two separate steps, not one combined
 * "subjects & teachers" step — they're two separate pages in Data Entry
 * (SubjectsSection.jsx / TeachersSection.jsx) now, so the progress
 * tracking matches the real structure of the work instead of glossing
 * over it.
 */
export function useSetupProgress({
  schoolId,
  classGroupId,
  classGroupLabel,
  // periods/subjects/teachers/constraints are all App.jsx's own state now
  // (see App.jsx's docstrings on why each was lifted out of its
  // originally-owning tab) — read directly here instead of independently
  // re-fetching them, since App.jsx already keeps them live and this hook
  // re-running its own fetch of the same lists on every tab switch was
  // the remaining cause of the header progress bar (and OverviewTab, and
  // ConstraintsTab itself) taking a visible beat to update even after
  // Data Entry's equivalent lag had already been fixed.
  periods = [],
  subjects = [],
  teachers = [],
  constraints = [],
  hasTimetable = false,
  // Every SubjectRequirement in the school — App.jsx's own state now,
  // always fully loaded (see App.jsx's docstring on why the old per-
  // section lazy cache had to go: TeachersSection's live workload total
  // needs every section's data at once, not just whichever ones happen
  // to have been visited). This section's own count is just a filter
  // over it, not a separate fetch.
  allRequirements = [],
}) {
  const loaded = Boolean(schoolId)
  // Nothing left for this hook to fetch itself — every count it reports
  // is derived from already-loaded state passed in, so there's nothing
  // that can fail here anymore. Kept in the return value (always null)
  // so OverviewTab/SetupProgressBar don't need to change how they read it.
  const loadError = null

  const requirementsCount = classGroupId
    ? allRequirements.filter((r) => r.class_group_id === classGroupId).length
    : 0

  const steps = [
    {
      key: 'periods',
      title: "Your school's daily schedule",
      body: periods.length > 0 ? `${periods.length} periods set up` : 'Add your period timings. Every class is built around this',
      done: periods.length > 0,
      optional: false,
      tab: 'entry',
      subView: 'setup',
    },
    {
      key: 'subjects',
      title: 'Subjects',
      body: subjects.length > 0 ? `${subjects.length} subjects added` : 'Add what your school teaches',
      done: subjects.length > 0,
      optional: false,
      tab: 'entry',
      subView: 'subjects',
    },
    {
      key: 'teachers',
      title: 'Teachers',
      body: teachers.length > 0 ? `${teachers.length} teachers added` : 'Add who teaches',
      done: teachers.length > 0,
      optional: false,
      tab: 'entry',
      subView: 'teachers',
    },
    {
      key: 'plan',
      title: classGroupLabel ? `What ${classGroupLabel} needs` : "This section's plan",
      body: requirementsCount > 0 ? `${requirementsCount} subjects planned` : 'Choose how many periods a week this section needs of each subject',
      done: requirementsCount > 0,
      optional: false,
      tab: 'entry',
      subView: 'plan',
    },
    {
      key: 'constraints',
      title: 'Any special rules?',
      body: constraints.length > 0 ? `${constraints.length} rules added` : "Optional. Skip if there's nothing special; you can add rules anytime",
      done: constraints.length > 0,
      optional: true,
      tab: 'constraints',
    },
    {
      key: 'generate',
      title: 'Build the timetable',
      body: hasTimetable ? 'Timetable ready' : 'One click builds a complete, conflict-free schedule',
      done: hasTimetable,
      optional: false,
      tab: 'timetable',
    },
  ]

  const requiredSteps = steps.filter((s) => !s.optional)
  const doneRequiredCount = requiredSteps.filter((s) => s.done).length
  const currentStep = steps.find((s) => !s.optional && !s.done)
  const allRequiredDone = requiredSteps.every((s) => s.done)

  return { steps, requiredSteps, doneRequiredCount, currentStep, allRequiredDone, loaded, loadError }
}
