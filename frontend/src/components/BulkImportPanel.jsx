import { useState } from 'react'
import { api } from '../api'

const RESOURCES = {
  subjects: { label: 'Subjects', columns: 'name, required_room_type' },
  rooms: { label: 'Rooms', columns: 'name, capacity, room_type' },
  teachers: { label: 'Teachers', columns: 'name, email, max_periods_per_week, qualified_subjects' },
  'class-groups': { label: 'Class groups (sections)', columns: 'name, grade, student_count' },
}

/**
 * Upload a CSV or .xlsx to create/update many rows at once, instead of
 * one at a time through the panels below. Upserts by name (see
 * backend/app/services/bulk_import.py) so re-uploading the same file
 * after fixing a typo updates rather than duplicates, and one bad row
 * doesn't block the rest of the file — the result summary below the
 * form always shows created/updated counts plus any per-row errors.
 *
 * Teachers' "qualified_subjects" column is matched against subjects
 * already in this school, so import subjects first if you're doing a
 * from-scratch setup.
 *
 * `resource` locks this panel to exactly one resource type — no dropdown
 * to switch it. Each embedding page (Subjects, Teachers) is already
 * unambiguous about what it imports, so offering "import rooms" from the
 * Teachers page (or vice versa) was a leftover from when this was one
 * shared panel with a "pick a resource" step; letting the Teachers page
 * import Subjects was actively confusing, not just superfluous.
 */
export default function BulkImportPanel({ schoolId, onImported, resource }) {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const meta = RESOURCES[resource]

  async function handleUpload(e) {
    e.preventDefault()
    if (!file) return
    setUploading(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.bulkImport(resource, schoolId, file)
      setResult(res)
      setFile(null)
      e.target.reset()
      if (onImported) await onImported()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-medium">Bulk import {meta.label.toLowerCase()}</h3>
      <p className="mt-1 text-xs text-slate-500">
        Upload a CSV or Excel file to add or update many at once instead of
        one at a time.
      </p>

      <form onSubmit={handleUpload} className="mt-3 flex flex-wrap items-center gap-2">
        {/* The native file input renders as plain text in some browsers,
            not obviously clickable next to the "Import" button — hidden
            (not removed, still what actually opens the file dialog and
            holds the value) in favor of a label styled to look like the
            other secondary buttons on this page. */}
        <input
          type="file"
          id={`bulk-import-file-${resource}`}
          accept=".csv,.xlsx"
          disabled={uploading}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="sr-only"
        />
        <label
          htmlFor={`bulk-import-file-${resource}`}
          className={`rounded-md border border-slate-300 px-3.5 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 ${
            uploading ? 'pointer-events-none opacity-50' : 'cursor-pointer'
          }`}
        >
          Choose file
        </label>
        {file && <span className="max-w-[200px] truncate text-sm text-slate-500">{file.name}</span>}
        <button
          disabled={!file || uploading}
          className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
        >
          {uploading ? 'Importing…' : 'Import'}
        </button>
        <a
          href={api.bulkImportTemplateUrl(resource)}
          className="text-xs text-slate-500 underline hover:text-slate-700"
        >
          Download template
        </a>
      </form>

      <p className="mt-2 text-xs text-slate-400">Columns: {meta.columns}</p>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {result && (
        <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs">
          <p className="font-medium text-slate-700">
            {result.created} created, {result.updated} updated
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
