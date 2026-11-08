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
export default function ClassPlanImport({ schoolId, file: givenFile, onDone }) {
  const [file, setFile] = useState(givenFile ?? null)
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
      setPreview(await api.classPlanPreview(schoolId, f))
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

  const questions = preview?.questions ?? []
  const unanswered = questions.filter((q) => !answers[q.id]).length

  return (
    <section aria-label="Fill in every class from your file" className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
      <p className="font-medium text-slate-900">Fill in every class from your file</p>
      <p className="mt-0.5 text-xs text-slate-600">
        If your staff sheet has a table for each class (Subjects, Periods, Teacher), we make the sections and fill in
        every plan from it.
      </p>

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
            id="class-plan-file"
            accept=".xlsx,.csv,.docx"
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <label htmlFor="class-plan-file" className="cursor-pointer rounded-md border border-slate-300 bg-white px-3.5 py-1.5 font-medium text-slate-700 hover:bg-slate-50">
            Choose file
          </label>
          {file && <span className="max-w-[220px] truncate text-slate-500">{file.name}</span>}
          <button disabled={!file || reading} className="rounded-md bg-neutral-900 px-3.5 py-1.5 font-medium text-white hover:bg-neutral-700 disabled:opacity-50">
            {reading ? 'Reading…' : 'Read file'}
          </button>
        </form>
      )}

      {error && <p className="mt-2 text-red-600">{error}</p>}

      {result && (
        <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-emerald-800" role="status">
          Done: {result.sections.length > 0 && `${result.sections.length} new sections, `}
          {result.requirements} subject plans
          {result.blocks > 0 && `, ${result.blocks} choice blocks`}
          {result.subjects.length > 0 && `, ${result.subjects.length} new subjects`}
          {result.teachers.length > 0 && `, ${result.teachers.length} new teachers`}.
        </p>
      )}

      {preview && (
        <div className="mt-3 flex flex-col gap-3">
          <p className="text-slate-800">
            We found plans for <strong>{preview.summary.classes} classes</strong>
            {preview.lessons_per_week ? ` (your week has ${preview.lessons_per_week} lessons)` : ''}.
          </p>
          {preview.skipped.length > 0 && (
            <p className="text-xs text-slate-600">Left out because they have 0 periods: {preview.skipped.join(', ')}.</p>
          )}
          {preview.new_subjects.length > 0 && (
            <p className="text-xs text-slate-600">New subjects that will be added: {preview.new_subjects.join(', ')}.</p>
          )}

          {preview.checks.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-amber-900">
              <p className="font-medium">Fix these first, or the timetable can’t be made</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs">
                {preview.checks.map((c) => <li key={c}>{c}</li>)}
              </ul>
              <p className="mt-1 text-xs">You can fill in the plans anyway and change them afterwards.</p>
            </div>
          )}

          {questions.length > 0 && (
            <div className="rounded-md border border-sky-200 bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">
                  {questions.length === 1 ? 'One question' : `${questions.length} questions`} so nothing is guessed
                </p>
                <button
                  type="button"
                  onClick={() => setAnswers(Object.fromEntries(questions.map((q) => [q.id, q.suggested])))}
                  className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50"
                >
                  Use the suggested answers
                </button>
              </div>
              <ol className="mt-2 space-y-3">
                {questions.map((q, i) => (
                  <li key={q.id}>
                    <fieldset>
                      <legend className="font-medium text-slate-800">{i + 1}. {q.text}</legend>
                      {q.note && <p className="text-xs text-slate-500">{q.note}</p>}
                      <div className="mt-1 flex flex-col gap-1">
                        {q.options.map((o) => (
                          <label key={o.key} className="flex cursor-pointer items-start gap-2 text-slate-700">
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
                  </li>
                ))}
              </ol>
            </div>
          )}

          <details className="rounded-md border border-slate-200 bg-white px-3 py-2">
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
                      <li key={it.id}>
                        {it.raw} · {it.periods} · {it.teachers.join(' / ') || 'no teacher'}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </details>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={save}
              disabled={saving || unanswered > 0}
              className="rounded-md bg-neutral-900 px-4 py-2 font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {saving
                ? 'Filling in…'
                : unanswered > 0
                  ? `Answer ${unanswered === 1 ? 'the question' : `${unanswered} questions`} to fill in the plans`
                  : 'Fill in the plans'}
            </button>
            <button type="button" onClick={() => setPreview(null)} className="rounded-md border border-slate-300 bg-white px-4 py-2 font-medium hover:bg-slate-50">
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
