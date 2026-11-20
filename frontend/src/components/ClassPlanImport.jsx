import { useEffect, useState } from 'react'
import { api } from '../api'

/**
 * Every section's weekly plan from the school's allotment sheet - a table per
 * class with Subjects, Periods and Teacher (backend app/services/class_plan.py).
 *
 * Reads the file, shows what it found, and asks about everything the sheet
 * leaves open (which sections, who a name is, whether two teachers split two
 * sections, how a combined entry like "Maths/Bio" should go). Nothing is saved
 * until every question is answered and the school clicks Fill in.
 */
const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function ClassPlanImport({
  schoolId,
  file: givenFile,
  onDone,
  inputId = 'class-plan-file',
  withStaffList = false,
  title = 'Fill in every class from your file',
  blurb = 'Upload your allotment or staff sheet, in any layout: a table per class, a grid of periods, a list under each teacher, or last year’s timetable (Excel, Word, CSV, a PDF or a photo). We make the sections and fill in every plan from it.',
}) {
  const [file, setFile] = useState(givenFile ?? null)
  const [staffFile, setStaffFile] = useState(null)
  const [reading, setReading] = useState(false)
  const [preview, setPreview] = useState(null)
  const [answers, setAnswers] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  async function read(f) {
    setReading(true)
    setError(null)
    setResult(null)
    try {
      setPreview(staffFile ? await api.classPlanPreview(schoolId, f, staffFile) : await api.classPlanPreview(schoolId, f))
      setAnswers({})
    } catch (err) {
      setError(err.message)
      setPreview(null)
    } finally {
      setReading(false)
    }
  }

  // The file from step 3: read it straight away.
  useEffect(() => {
    if (givenFile) {
      setFile(givenFile)
      read(givenFile)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [givenFile])

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const res = await api.classPlanCommit(schoolId, preview.plan, answers)
      setResult(res)
      setPreview(null)
      await onDone?.(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label={title} className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
      <p className="font-medium text-slate-900">{title}</p>
      <p className="mt-0.5 text-xs text-slate-600">{blurb}</p>

      {!preview && (
        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (file) read(file)
          }}
        >
          <input
            type="file"
            id={inputId}
            accept=".xlsx,.csv,.docx,.pdf,.png,.jpg,.jpeg,.webp"
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <label htmlFor={inputId} className="cursor-pointer rounded-md border border-slate-300 bg-white px-3.5 py-1.5 font-medium text-slate-700 hover:bg-slate-50">
            Choose file
          </label>
          {file && <span className="max-w-[220px] truncate text-slate-500">{file.name}</span>}
          {withStaffList && (
            <>
              <input
                type="file"
                id={`${inputId}-staff`}
                accept=".xlsx,.csv,.docx,.pdf,.png,.jpg,.jpeg,.webp"
                className="sr-only"
                onChange={(e) => setStaffFile(e.target.files?.[0] ?? null)}
              />
              <label
                htmlFor={`${inputId}-staff`}
                className="cursor-pointer rounded-md border border-dashed border-slate-300 bg-white px-3.5 py-1.5 text-slate-600 hover:bg-slate-50"
              >
                {staffFile ? `Staff list: ${staffFile.name}` : '+ Staff list (optional)'}
              </label>
            </>
          )}
          <button disabled={!file || reading} className="rounded-md bg-neutral-900 px-3.5 py-1.5 font-medium text-white hover:bg-neutral-700 disabled:opacity-50">
            {reading ? 'Reading…' : 'Read file'}
          </button>
        </form>
      )}

      {withStaffList && !preview && (
        <p className="mt-1.5 text-xs text-slate-500">
          Add your staff list too and every short name in the timetable (“KRITHI”, “V’G”, “SUBHA”) is matched to the
          full name on it, using the subject where two names are alike. Everyone on the list is added as a teacher.
        </p>
      )}

      {error && <p className="mt-2 text-red-600">{error}</p>}

      {result && (
        <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-emerald-800" role="status">
          Done: {result.sections.length > 0 && `${result.sections.length} new sections, `}
          {result.requirements} subject plans
          {result.blocks > 0 && `, ${result.blocks} choice blocks`}
          {result.subjects.length > 0 && `, ${result.subjects.length} new subjects`}
          {result.teachers.length > 0 && `, ${result.teachers.length} new teachers`}
          {result.periods > 0 && `, and your week (${result.periods} periods)`}
          {result.fixed > 0 && `, ${result.fixed} fixed periods`}.
          {result.kept_as_version && (
            <>
              {' '}Last year’s timetable is kept as Version {result.kept_as_version.version} ({result.kept_as_version.lessons}{' '}
              lessons{result.kept_as_version.not_placed > 0 ? `, ${result.kept_as_version.not_placed} that didn’t fit your week left out` : ''}):
              open it on the Timetable tab.
            </>
          )}
        </p>
      )}

      {preview && (
        <PreviewSteps
          preview={preview}
          answers={answers}
          setAnswers={setAnswers}
          saving={saving}
          onSave={save}
          onCancel={() => setPreview(null)}
        />
      )}
    </section>
  )
}

/**
 * What was read, one box at a time: what the file is, the week, the
 * teachers and subjects it adds, what's worth checking, then each question
 * on its own, and last the plans themselves with the button that saves them.
 * Back and Next move between boxes; a question's Next waits for an answer.
 */
function PreviewSteps({ preview, answers, setAnswers, saving, onSave, onCancel }) {
  const questions = preview.questions ?? []
  const steps = []
  steps.push({ key: 'read', title: 'What we read' })
  if (preview.new_teachers?.length > 0 || preview.staff_listed > 0) steps.push({ key: 'teachers', title: 'Teachers' })
  if (preview.new_subjects?.length > 0) steps.push({ key: 'subjects', title: 'Subjects' })
  if (preview.checks?.length > 0) steps.push({ key: 'checks', title: 'Worth checking' })
  questions.forEach((q, i) => steps.push({ key: `q:${q.id}`, title: `Question ${i + 1} of ${questions.length}`, q }))
  steps.push({ key: 'done', title: 'Ready to fill in' })
  const [at, setAt] = useState(0)
  const step = steps[Math.min(at, steps.length - 1)]
  const unanswered = questions.filter((q) => !answers[q.id])
  const waiting = step.q && !answers[step.q.id]

  function applySuggested() {
    setAnswers(Object.fromEntries(questions.map((q) => [q.id, answers[q.id] ?? q.suggested])))
    setAt(steps.length - 1)
  }

  return (
    <div className="mt-3 flex flex-col gap-3">
      <ol aria-label="Steps" className="flex flex-wrap gap-1.5">
        {steps.map((s, i) => {
          const answered = s.q && answers[s.q.id]
          return (
            <li key={s.key}>
              <button
                type="button"
                onClick={() => setAt(i)}
                aria-current={i === at ? 'step' : undefined}
                aria-label={`Go to step ${i + 1}: ${s.title}`}
                className={`h-2 rounded-full transition-all ${i === at ? 'w-6 bg-neutral-900'
                  : answered || (!s.q && i < at) ? 'w-2 bg-emerald-500' : s.q ? 'w-2 bg-sky-300' : 'w-2 bg-slate-300'}`}
              />
            </li>
          )
        })}
      </ol>

      <div className="rounded-lg border border-slate-200 bg-white p-4" role="group" aria-label={step.title}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Step {at + 1} of {steps.length} · {step.title}
          </p>
          {questions.length > 0 && step.key !== 'done' && (
            <button
              type="button"
              onClick={applySuggested}
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50"
            >
              Use the suggested answers
            </button>
          )}
        </div>
        <div className="mt-2">
          <StepBody step={step} preview={preview} answers={answers} setAnswers={setAnswers} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {at > 0 && (
          <button type="button" onClick={() => setAt(at - 1)}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 font-medium hover:bg-slate-50">
            Back
          </button>
        )}
        {step.key !== 'done' ? (
          <button
            type="button"
            onClick={() => setAt(at + 1)}
            disabled={waiting}
            className="rounded-md bg-neutral-900 px-4 py-2 font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {waiting ? 'Pick an answer to go on' : 'Next'}
          </button>
        ) : (
          <button
            type="button"
            onClick={unanswered.length ? () => setAt(steps.findIndex((s) => s.q && !answers[s.q.id])) : onSave}
            disabled={saving}
            className="rounded-md bg-neutral-900 px-4 py-2 font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {saving
              ? 'Filling in…'
              : unanswered.length
                ? `Answer ${unanswered.length === 1 ? 'the question' : `${unanswered.length} questions`} first`
                : 'Fill in the plans'}
          </button>
        )}
        <button type="button" onClick={onCancel} className="ml-auto text-sm text-slate-500 underline-offset-2 hover:underline">
          Cancel
        </button>
      </div>
    </div>
  )
}

function Chips({ items }) {
  return (
    <ul className="mt-1.5 flex flex-wrap gap-1.5">
      {items.map((x) => (
        <li key={x} className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700">{x}</li>
      ))}
    </ul>
  )
}

function StepBody({ step, preview, answers, setAnswers }) {
  if (step.key === 'read') {
    return (
      <div className="flex flex-col gap-2 text-slate-700">
        <p className="text-slate-800">
          We found plans for <strong>{preview.summary.classes} classes</strong>
          {preview.lessons_per_week ? ` (your week has ${preview.lessons_per_week} lessons)` : ''}.
        </p>
        {preview.from_timetable && (
          <p className="text-xs text-slate-600">
            Read as last year’s timetable: each section’s periods of every subject counted from its week, with the
            teacher who took them and the class teacher.
          </p>
        )}
        {preview.week && (
          <p className="text-xs text-slate-600">
            Your week isn’t set up yet, so we’ll use last year’s:{' '}
            {preview.week.days.map((d) => DAY_NAMES[d]).join(', ')}, {preview.week.periods} periods a day
            {preview.week.breaks?.length > 0
              ? `, with ${preview.week.breaks.map((b) => `${b.name.toLowerCase()} after period ${b.after}`).join(' and ')}`
              : ''}
            . You can change it afterwards in Setup.
          </p>
        )}
        {preview.found?.length > 0 && (
          <div className="text-xs text-slate-600">
            <p>Also read from the timetable:</p>
            <ul className="mt-0.5 list-disc pl-4">
              {preview.found.map((f) => <li key={f}>{f}</li>)}
            </ul>
          </div>
        )}
        {preview.skipped?.length > 0 && (
          <p className="text-xs text-slate-600">Left out because they have 0 periods: {preview.skipped.join(', ')}.</p>
        )}
      </div>
    )
  }
  if (step.key === 'teachers') {
    return (
      <div className="text-sm text-slate-700">
        {preview.staff_listed > 0 && (
          <p className="text-xs text-slate-600">Names matched to your staff list ({preview.staff_listed} people).</p>
        )}
        {preview.new_teachers?.length > 0 ? (
          <>
            <p className="mt-1">New teachers that will be added ({preview.new_teachers.length}):</p>
            <Chips items={preview.new_teachers} />
          </>
        ) : <p className="mt-1">No new teachers: everyone is already here.</p>}
      </div>
    )
  }
  if (step.key === 'subjects') {
    return (
      <div className="text-sm text-slate-700">
        <p>New subjects that will be added ({preview.new_subjects.length}):</p>
        <Chips items={preview.new_subjects} />
        <p className="mt-2 text-xs text-slate-500">A short code nobody knows yet (like “ESK”) is asked about next.</p>
      </div>
    )
  }
  if (step.key === 'checks') {
    return (
      <div className="text-amber-900">
        <p className="font-medium">Worth checking before the timetable is made</p>
        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
          {preview.checks.map((c) => <li key={c}>{c}</li>)}
        </ul>
        <p className="mt-2 text-xs">You can fill in the plans anyway and change them afterwards.</p>
      </div>
    )
  }
  if (step.q) {
    const q = step.q
    return (
      <fieldset>
        <legend className="font-medium text-slate-800">{q.text}</legend>
        {q.note && <p className="mt-0.5 text-xs text-slate-500">{q.note}</p>}
        <div className="mt-2 flex flex-col gap-1.5">
          {q.options.map((o) => (
            <label key={o.key} className={`flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-slate-700 ${
              answers[q.id] === o.key ? 'border-neutral-900 bg-slate-50' : 'border-slate-200 hover:bg-slate-50'}`}>
              <input
                type="radio"
                name={`plan-${q.id}`}
                className="mt-0.5"
                checked={answers[q.id] === o.key}
                onChange={() => setAnswers((a) => ({ ...a, [q.id]: o.key }))}
              />
              <span>
                {o.label}
                {o.key === q.suggested && <span className="ml-1 text-xs text-slate-400">(suggested)</span>}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
    )
  }
  // The last box: the plans as they'll be saved.
  return (
    <div className="text-sm text-slate-700">
      <p>
        Ready to fill in {preview.summary.classes} classes
        {preview.summary.subjects ? ` (${preview.summary.subjects} subject plans)` : ''}.
      </p>
      <details className="mt-2 rounded-md border border-slate-200 px-3 py-2">
        <summary className="cursor-pointer font-medium">What we read for each class</summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          {preview.plan.tables.map((t) => (
            <div key={t.id}>
              <p className="font-medium text-slate-800">
                {t.label}
                <span className="ml-1 text-xs font-normal text-slate-500">
                  {t.sections_q ? '(sections: see question)' : `→ ${t.sections.map((x) => `${t.grade} ${x}`).join(', ')}`}
                </span>
              </p>
              <ul className="text-xs text-slate-600">
                {t.items.map((it) => (
                  <li key={it.id}>{it.raw} · {it.periods} · {it.teachers.join(' / ') || 'no teacher'}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </details>
    </div>
  )
}
