import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import TimetableStructurePanel from './TimetableStructurePanel'
import BulkAddClassGroups from './BulkAddClassGroups'
import BulkImportPanel from './BulkImportPanel'
import StandardRules from './StandardRules'
import SetupCheckPanel from './SetupCheckPanel'
import ClassPlanImport from './ClassPlanImport'

/**
 * "Get started": the whole way from a new school to a timetable on one page,
 * one step at a time, without needing to know what Setup, Data Entry or
 * Constraints mean. Each step is the same panel the tabs use (so anything
 * done here is the same as doing it there, and the tabs stay for editing
 * later); this page only puts them in order, says what each is for, and
 * opens the next one.
 *
 *   1. Your school day      TimetableStructurePanel
 *   2. Your classes         BulkAddClassGroups
 *   3. Teachers & subjects  BulkImportPanel (the staff list brings its subjects)
 *   4. What each class needs  every section's weekly plan, with a link into it
 *   5. Any rules?           StandardRules, plus a link to write one's own
 *   6. Build the timetable  the setup check, then Generate
 */
export default function GetStartedTab({
  school,
  periods = [],
  classGroups = [],
  subjects = [],
  teachers = [],
  allRequirements = [],
  readOnly = false,
  onReload,
  onAddClassGroups,
  onOpenSection,
  onOpenTab,
  onSaveStandardRules,
  onFix,
  onGenerate,
}) {
  const schoolId = school.id
  const grades = useMemo(() => [...new Set(classGroups.map((c) => c.grade).filter(Boolean))], [classGroups])
  const lessonsPerWeek = periods.filter((p) => (p.kind ?? (p.is_break ? 'break' : 'lesson')) === 'lesson').length
  const planBySection = useMemo(() => {
    const m = new Map()
    for (const r of allRequirements) {
      const cur = m.get(r.class_group_id) ?? { subjects: 0, periods: 0 }
      m.set(r.class_group_id, { subjects: cur.subjects + 1, periods: cur.periods + (r.periods_per_week || 0) })
    }
    return m
  }, [allRequirements])
  const sectionsPlanned = classGroups.filter((c) => planBySection.get(c.id)?.subjects > 0).length

  const steps = [
    {
      key: 'day',
      title: 'Your school day',
      why: 'Which days you work, how many periods, and where the breaks are. Everything is built around this.',
      status: periods.length ? `${lessonsPerWeek} lessons a week` : 'Not set yet',
      done: periods.length > 0,
    },
    {
      key: 'classes',
      title: 'Your classes',
      why: 'Every section that needs a timetable, like 6A, 6B and 7A.',
      status: classGroups.length ? `${classGroups.length} sections` : 'None yet',
      done: classGroups.length > 0,
    },
    {
      key: 'staff',
      title: 'Your teachers and subjects',
      why: 'Upload the staff list you already have. We read the teachers, what they teach and which classes, and add the subjects.',
      status: teachers.length ? `${teachers.length} teachers, ${subjects.length} subjects` : 'None yet',
      done: teachers.length > 0 && subjects.length > 0,
    },
    {
      key: 'plan',
      title: 'What each class needs',
      why: 'For each section, how many periods a week of each subject, and who teaches it.',
      status: classGroups.length ? `${sectionsPlanned} of ${classGroups.length} sections done` : 'Add classes first',
      done: classGroups.length > 0 && sectionsPlanned === classGroups.length,
    },
    {
      key: 'rules',
      title: 'Any rules?',
      why: 'Optional. Common ones are ready to tick; anything special you can write in plain English.',
      status: 'Optional',
      done: false,
      optional: true,
    },
    {
      key: 'build',
      title: 'Build the timetable',
      why: 'We check everything is in place, then build a clash-free timetable for every section.',
      status: '',
      done: false,
    },
  ]
  const firstOpen = steps.find((s) => !s.done && !s.optional)?.key ?? 'build'
  const [open, setOpen] = useState(firstOpen)
  // The staff sheet from step 3, read again in step 4 for every class's plan.
  const [staffFile, setStaffFile] = useState(null)
  const requiredLeft = steps.filter((s) => !s.optional && s.key !== 'build' && !s.done)

  function next(key) {
    const i = steps.findIndex((s) => s.key === key)
    setOpen(steps[i + 1]?.key ?? null)
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Get started</h1>
        <p className="mt-1 text-sm text-slate-600">
          Six steps from here to a finished timetable. Do them in order; you can come back and change anything later.
        </p>
      </header>

      {!readOnly && (
        <ClassPlanImport
          schoolId={schoolId}
          inputId="last-year-file-start"
          withStaffList
          title="Have last year’s timetable? Start from it"
          blurb="Upload it first and we set up every section and class teacher, the subjects, the teachers, each subject’s periods and who taught them, and your week. The steps below then show as done, and you only change what’s different this year."
          onDone={onReload}
        />
      )}

      <ol className="flex flex-col gap-3">
        {steps.map((s, i) => {
          const isOpen = open === s.key
          return (
            <li key={s.key} className={`rounded-xl border bg-white ${isOpen ? 'border-neutral-900' : 'border-slate-200'}`}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : s.key)}
                aria-expanded={isOpen}
                className="flex w-full items-center gap-3 px-5 py-4 text-left"
              >
                <span
                  aria-hidden="true"
                  className={`flex h-7 w-7 flex-none items-center justify-center rounded-full text-xs font-semibold ${
                    s.done ? 'bg-emerald-600 text-white' : isOpen ? 'bg-neutral-900 text-white' : 'border border-slate-300 text-slate-500'
                  }`}
                >
                  {s.done ? '✓' : i + 1}
                </span>
                <span className="flex-1">
                  <span className="block font-medium text-slate-900">{s.title}</span>
                  {!isOpen && s.status && <span className="block text-xs text-slate-500">{s.status}</span>}
                </span>
                {s.done && <span className="text-xs font-medium text-emerald-700">Done</span>}
              </button>

              {isOpen && (
                <div className="border-t border-slate-100 px-5 py-4">
                  <p className="mb-4 text-sm text-slate-600">{s.why}</p>

                  {s.key === 'day' && (
                    <TimetableStructurePanel schoolId={schoolId} grades={grades} onSaved={onReload} readOnly={readOnly} />
                  )}

                  {s.key === 'classes' && (
                    <div className="flex flex-col gap-3">
                      <p className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
                        Have a sheet with a table for each class (Subjects, Periods, Teacher)? Skip this: step 4 makes the
                        sections from it.
                      </p>
                      {classGroups.length > 0 && (
                        <p className="text-sm text-slate-700">
                          Already added:{' '}
                          {classGroups.map((c) => `${c.grade ? `${c.grade} ` : ''}${c.name}`).join(', ')}
                        </p>
                      )}
                      {!readOnly && (
                        <BulkAddClassGroups
                          onAddClassGroups={onAddClassGroups}
                          existing={classGroups}
                          institutionType={school.institution_type}
                          compact
                        />
                      )}
                    </div>
                  )}

                  {s.key === 'staff' && (
                    <div className="flex flex-col gap-3">
                      {!readOnly && <BulkImportPanel schoolId={schoolId} resource="teachers" onImported={onReload} onFileRead={setStaffFile} />}
                      <p className="text-xs text-slate-500">
                        No file?{' '}
                        <button type="button" onClick={() => onOpenTab('entry', 'subjects')} className="underline hover:text-slate-700">
                          Add subjects
                        </button>{' '}
                        and{' '}
                        <button type="button" onClick={() => onOpenTab('entry', 'teachers')} className="underline hover:text-slate-700">
                          teachers
                        </button>{' '}
                        by hand instead.
                      </p>
                    </div>
                  )}

                  {s.key === 'plan' && !readOnly && (
                    <div className="mb-4">
                      <ClassPlanImport schoolId={schoolId} file={staffFile} onDone={onReload} />
                    </div>
                  )}
                  {s.key === 'plan' && (
                    classGroups.length === 0 ? (
                      <p className="text-sm text-slate-500">No sections yet: fill them in from your file above, or add them in step 2.</p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <table className="w-full text-left text-sm">
                          <thead className="text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="py-1.5 font-medium">Section</th>
                              <th className="py-1.5 font-medium">Planned</th>
                              <th className="py-1.5" />
                            </tr>
                          </thead>
                          <tbody>
                            {classGroups.map((c) => {
                              const p = planBySection.get(c.id)
                              const full = lessonsPerWeek > 0 && p?.periods === lessonsPerWeek
                              return (
                                <tr key={c.id} className="border-t border-slate-100">
                                  <td className="py-2 font-medium">{`${c.grade ? `${c.grade} ` : ''}${c.name}`}</td>
                                  <td className={`py-2 ${p ? (full ? 'text-emerald-700' : 'text-slate-700') : 'text-amber-700'}`}>
                                    {p
                                      ? `${p.subjects} subjects, ${p.periods}${lessonsPerWeek ? ` of ${lessonsPerWeek}` : ''} periods`
                                      : 'Nothing yet'}
                                  </td>
                                  <td className="py-2 text-right">
                                    <button
                                      type="button"
                                      onClick={() => onOpenSection(c.id, 'plan')}
                                      className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium hover:bg-slate-50"
                                    >
                                      {p ? 'Edit' : 'Fill in'}
                                    </button>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                        <p className="text-xs text-slate-500">
                          Tip: fill in one section, then copy its plan to the others in the same class from inside the plan.
                        </p>
                      </div>
                    )
                  )}

                  {s.key === 'rules' && (
                    <div className="flex flex-col gap-3">
                      <StandardRules rules={school.standard_rules ?? null} onSave={onSaveStandardRules} readOnly={readOnly} subjects={subjects} />
                      <button type="button" onClick={() => onOpenTab('constraints')} className="w-fit text-sm underline hover:text-slate-700">
                        Write a rule of your own (like “No Maths in the last period”)
                      </button>
                    </div>
                  )}

                  {s.key === 'build' && (
                    <BuildStep schoolId={schoolId} requiredLeft={requiredLeft} onFix={onFix} onGenerate={onGenerate} readOnly={readOnly} />
                  )}

                  {s.key !== 'build' && (
                    <div className="mt-5 flex justify-end">
                      <button
                        type="button"
                        onClick={() => next(s.key)}
                        className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
                      >
                        {s.optional ? 'Next' : s.done ? 'Next step' : 'Skip for now'}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function BuildStep({ schoolId, requiredLeft, onFix, onGenerate, readOnly }) {
  const [check, setCheck] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let live = true
    setLoading(true)
    api
      .setupCheck(schoolId)
      .then((c) => live && setCheck(c))
      .catch(() => live && setCheck(null))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [schoolId])

  return (
    <div className="flex flex-col gap-4">
      {requiredLeft.length > 0 && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Still to do: {requiredLeft.map((s) => s.title.toLowerCase()).join(', ')}.
        </p>
      )}
      <SetupCheckPanel check={check} loading={loading} onFix={onFix} readOnly={readOnly} schoolId={schoolId} />
      {!readOnly && (
        <div>
          <button
            type="button"
            onClick={onGenerate}
            disabled={requiredLeft.length > 0}
            className="rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            Build my timetable
          </button>
        </div>
      )}
    </div>
  )
}
