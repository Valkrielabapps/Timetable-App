import { useState } from 'react'
import { api } from '../api'

/**
 * Upload an arbitrary spreadsheet the admin already has lying around —
 * an old staff list, a manually-made timetable export, whatever — that
 * isn't in BulkImportPanel's expected column format. Claude reads it and
 * proposes teachers/subjects/class groups; nothing is created until the
 * admin reviews the preview below (unchecking anything wrong) and clicks
 * Create. See backend/app/services/setup_extractor.py for the extraction
 * contract: CSV/.xlsx only (no PDF yet), best-effort on messy input.
 *
 * State machine: idle -> extracting -> reviewing (preview shown, items
 * individually checked/unchecked) -> committing -> done (summary shown,
 * resets to idle on a fresh upload).
 */
export default function SetupExtractionPanel({ schoolId, onImported }) {
  const [file, setFile] = useState(null)
  const [extracting, setExtracting] = useState(false)
  const [error, setError] = useState(null)
  const [preview, setPreview] = useState(null) // { teachers, subjects, class_groups, notes }
  const [selected, setSelected] = useState(null) // parallel arrays of booleans
  const [committing, setCommitting] = useState(false)
  const [result, setResult] = useState(null)

  async function handleExtract(e) {
    e.preventDefault()
    if (!file) return
    setExtracting(true)
    setError(null)
    setPreview(null)
    setResult(null)
    try {
      const res = await api.extractSetup(schoolId, file)
      setPreview(res)
      setSelected({
        teachers: res.teachers.map(() => true),
        subjects: res.subjects.map(() => true),
        class_groups: res.class_groups.map(() => true),
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setExtracting(false)
    }
  }

  function toggle(kind, index) {
    setSelected((prev) => ({
      ...prev,
      [kind]: prev[kind].map((v, i) => (i === index ? !v : v)),
    }))
  }

  async function handleCommit() {
    setCommitting(true)
    setError(null)
    try {
      const payload = {
        subjects: preview.subjects.filter((_, i) => selected.subjects[i]),
        teachers: preview.teachers.filter((_, i) => selected.teachers[i]),
        class_groups: preview.class_groups.filter((_, i) => selected.class_groups[i]),
      }
      const res = await api.commitSetupExtraction(schoolId, payload)
      setResult(res)
      setPreview(null)
      setSelected(null)
      setFile(null)
      if (onImported) await onImported()
    } catch (err) {
      setError(err.message)
    } finally {
      setCommitting(false)
    }
  }

  const selectedCount = selected
    ? selected.teachers.filter(Boolean).length +
      selected.subjects.filter(Boolean).length +
      selected.class_groups.filter(Boolean).length
    : 0

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-medium">Extract setup from a document</h3>
      <p className="mt-1 text-xs text-slate-500">
        Already have a staff list or an old timetable in a spreadsheet? Upload it as-is —
        no need to reformat it to match Bulk Import's columns — and Claude will suggest
        teachers, subjects, and class groups to create. You review and confirm before
        anything is added. CSV or Excel only for now.
      </p>

      {!preview && (
        <form onSubmit={handleExtract} className="mt-3 flex flex-wrap items-center gap-2">
          <input
            type="file"
            id={`setup-extraction-file-${schoolId}`}
            accept=".csv,.xlsx"
            disabled={extracting}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="sr-only"
          />
          <label
            htmlFor={`setup-extraction-file-${schoolId}`}
            className={`rounded-md border border-slate-300 px-3.5 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 ${
              extracting ? 'pointer-events-none opacity-50' : 'cursor-pointer'
            }`}
          >
            Choose file
          </label>
          {file && <span className="max-w-[200px] truncate text-sm text-slate-500">{file.name}</span>}
          <button
            disabled={!file || extracting}
            className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {extracting ? 'Reading…' : 'Extract'}
          </button>
        </form>
      )}

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {preview && selected && (
        <div className="mt-3 rounded-md border border-slate-200 p-3">
          <p className="text-xs font-medium text-slate-700">
            Review what Claude found, uncheck anything wrong, then confirm.
          </p>
          {preview.notes && (
            <p className="mt-1.5 rounded bg-amber-50 p-2 text-xs text-amber-800">{preview.notes}</p>
          )}

          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <ReviewList
              label="Subjects"
              items={preview.subjects}
              selected={selected.subjects}
              onToggle={(i) => toggle('subjects', i)}
              renderLabel={(s) => s.name}
            />
            <ReviewList
              label="Teachers"
              items={preview.teachers}
              selected={selected.teachers}
              onToggle={(i) => toggle('teachers', i)}
              renderLabel={(t) => t.name + (t.subject_names?.length ? ` — ${t.subject_names.join(', ')}` : '')}
            />
            <ReviewList
              label="Class groups"
              items={preview.class_groups}
              selected={selected.class_groups}
              onToggle={(i) => toggle('class_groups', i)}
              renderLabel={(g) => (g.grade ? `${g.grade} - ${g.name}` : g.name)}
            />
          </div>

          <div className="mt-3 flex items-center gap-2">
            <button
              onClick={handleCommit}
              disabled={committing || selectedCount === 0}
              className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {committing ? 'Creating…' : `Create ${selectedCount} selected`}
            </button>
            <button
              onClick={() => {
                setPreview(null)
                setSelected(null)
              }}
              disabled={committing}
              className="rounded-md border border-slate-300 px-3.5 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs">
          <p className="font-medium text-slate-700">
            {result.subjects_created + result.teachers_created + result.class_groups_created} created,{' '}
            {result.subjects_updated + result.teachers_updated + result.class_groups_updated} updated
            {result.errors.length > 0 && `, ${result.errors.length} row(s) skipped`}
          </p>
          {result.errors.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-amber-700">
              {result.errors.map((msg, i) => (
                <li key={i}>{msg}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function ReviewList({ label, items, selected, onToggle, renderLabel }) {
  return (
    <div>
      <h6 className="text-xs font-medium text-slate-500">
        {label} ({items.length})
      </h6>
      {items.length === 0 ? (
        <p className="mt-1 text-xs text-slate-400">None found</p>
      ) : (
        <ul className="mt-1 max-h-40 space-y-1 overflow-y-auto">
          {items.map((item, i) => (
            <li key={i}>
              <label className="flex items-start gap-1.5 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={selected[i]}
                  onChange={() => onToggle(i)}
                  className="mt-0.5"
                />
                <span className={selected[i] ? '' : 'text-slate-400 line-through'}>{renderLabel(item)}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
