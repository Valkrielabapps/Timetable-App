import { useState } from 'react'
import { api } from '../api'

const RESOURCES = {
  subjects: {
    label: 'Subjects',
    columns: 'name, required_room_type',
    smart: 'Upload the subject list you already have, in any layout. We find the subject names and room types ourselves, and show you what we found before anything is saved.',
  },
  rooms: { label: 'Rooms', columns: 'name, capacity, room_type' },
  teachers: {
    label: 'Teachers',
    columns: 'name, email, max_periods_per_week, qualified_subjects, qualified_grades (empty = every grade)',
    note: 'A teacher who is already here keeps what they teach: the file adds its subjects and grades to theirs. Remove one on the teacher\u2019s own row.',
    smart: 'Upload the staff list you already have, in any layout. We find the names, subjects, classes and workload ourselves, even from a grid of ticks, match spellings like \u201cMaths\u201d and \u201cStd 9\u201d to yours, and add any subject that isn\u2019t here yet. You see it all before anything is saved.',
  },
  'class-groups': { label: 'Class groups (sections)', columns: 'name, grade, student_count' },
}

/**
 * Upload a CSV or .xlsx to create/update many rows at once, instead of
 * one at a time through the panels below. Upserts by name (see
 * backend/app/services/bulk_import.py) so re-uploading the same file
 * after fixing a typo updates rather than duplicates, and one bad row
 * doesn't block the rest of the file - the result summary below the
 * form always shows created/updated counts plus any per-row errors.
 *
 * Teachers' "qualified_subjects" column is matched against subjects
 * already in this school, so import subjects first if you're doing a
 * from-scratch setup. Their "qualified_grades" column is matched against
 * the grades of the school's sections ("6", "Class 6" and "Grade 6" all
 * work, "6-8" is a range), and an empty cell means every grade.
 *
 * `resource` locks this panel to exactly one resource type - no dropdown
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
  // A school's own sheet is shown first and saved only on Import.
  const [preview, setPreview] = useState(null)
  const [saving, setSaving] = useState(false)

  const meta = RESOURCES[resource]

  async function handleUpload(e) {
    e.preventDefault()
    if (!file) return
    setUploading(true)
    setError(null)
    setResult(null)
    setPreview(null)
    try {
      if (meta.smart) {
        setPreview(await api.bulkImportPreview(resource, schoolId, file))
      } else {
        setResult(await api.bulkImport(resource, schoolId, file))
        if (onImported) await onImported()
      }
      setFile(null)
      e.target.reset()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  async function handleCommit() {
    setSaving(true)
    setError(null)
    try {
      const res = await api.bulkImportCommit(resource, schoolId, preview.rows)
      // Keep how it was read alongside what was saved.
      setResult({ ...res, sheet: preview.sheet, read_as: preview.read_as, matched: preview.matched })
      setPreview(null)
      if (onImported) await onImported()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-medium">Bulk import {meta.label.toLowerCase()}</h3>
      <p className="mt-1 text-xs text-slate-500">
        {meta.smart ?? 'Upload a CSV or Excel file to add or update many at once instead of one at a time.'}
      </p>
      {meta.note && <p className="mt-1 text-xs text-slate-500">{meta.note}</p>}

      <form onSubmit={handleUpload} className="mt-3 flex flex-wrap items-center gap-2">
        {/* The native file input renders as plain text in some browsers,
            not obviously clickable next to the "Import" button - hidden
            (not removed, still what actually opens the file dialog and
            holds the value) in favor of a label styled to look like the
            other secondary buttons on this page. */}
        <input
          type="file"
          id={`bulk-import-file-${resource}`}
          accept=".csv,.xlsx"
          disabled={uploading || saving}
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
          disabled={!file || uploading || saving}
          className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
        >
          {meta.smart ? (uploading ? 'Reading…' : 'Read file') : uploading ? 'Importing…' : 'Import'}
        </button>
        <a
          href={api.bulkImportTemplateUrl(resource)}
          className="text-xs text-slate-500 underline hover:text-slate-700"
        >
          Download template
        </a>
      </form>

      {!meta.smart && <p className="mt-2 text-xs text-slate-400">Columns: {meta.columns}</p>}

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {preview && (
        <ImportPreview
          preview={preview}
          saving={saving}
          onImport={handleCommit}
          onCancel={() => setPreview(null)}
        />
      )}

      {result && (
        <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs">
          <p className="font-medium text-slate-700">
            {result.created} created, {result.updated} updated
            {result.errors.length > 0 && `, ${result.errors.length} row(s) skipped`}
          </p>
          {result.read_as?.length > 0 && (
            <p className="mt-1.5 text-slate-600">
              Read {result.sheet && result.sheet !== 'CSV' ? `the sheet \u201c${result.sheet}\u201d, ` : ''}
              taking {result.read_as.join(', ')}.
            </p>
          )}
          {result.matched?.length > 0 && (
            <p className="mt-1 text-slate-600">Matched {result.matched.join(', ')}.</p>
          )}
          {result.new_subjects?.length > 0 && (
            <p className="mt-1 text-slate-600">
              Added {result.new_subjects.length === 1 ? 'a new subject' : `${result.new_subjects.length} new subjects`}:{' '}
              {result.new_subjects.join(', ')}.
            </p>
          )}
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

const FIRST_ROWS = 8

function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`
}

/**
 * The sheet as it will be saved, before anything is: how it was read, the
 * first rows (and any row with something to check), readings only the AI
 * made in amber, and what the checks found. Import saves exactly these rows.
 */
function ImportPreview({ preview, saving, onImport, onCancel }) {
  const teachers = preview.kind === 'teachers'
  const doubtful = new Set(preview.doubtful)
  const notes = preview.row_notes
  const shown = preview.rows
    .map((row, i) => ({ row, i, notes: notes[i] || [] }))
    .filter(({ i, notes: n }) => i < FIRST_ROWS || n.length > 0)
    .slice(0, FIRST_ROWS + 12)
  const hidden = preview.total - shown.length
  const what = teachers ? 'teacher' : 'subject'

  return (
    <section aria-label="Check before importing" className="mt-3 rounded-md border border-slate-200 bg-white p-3 text-xs">
      <p className="text-sm font-medium text-slate-800">
        We found {plural(preview.total, what)}
        {teachers && ` and ${plural(preview.subject_count, 'subject')}`}. Here’s how we read it.
      </p>
      {preview.read_as.length > 0 && (
        <p className="mt-1 text-slate-600">
          {preview.sheet && preview.sheet !== 'CSV' ? `From the sheet \u201c${preview.sheet}\u201d, taking ` : 'Taking '}
          {preview.read_as.join(', ')}.
        </p>
      )}
      {preview.matched.length > 0 && (
        <p className="mt-1 text-slate-600">
          Matched{' '}
          {preview.matched.map((m, i) => (
            <span key={m}>
              {i > 0 && ', '}
              {doubtful.has(m) ? (
                <mark className="rounded bg-amber-100 px-0.5 text-amber-900" title="Only the AI read it this way: check it">
                  {m}?
                </mark>
              ) : (
                m
              )}
            </span>
          ))}
          .
        </p>
      )}
      {preview.new_subjects.length > 0 && (
        <p className="mt-1 text-slate-600">
          {plural(preview.new_subjects.length, 'new subject')} will be added: {preview.new_subjects.join(', ')}.
        </p>
      )}
      {preview.will_update > 0 && (
        <p className="mt-1 text-slate-600">
          {plural(preview.will_update, `${what} is`, `${what}s are`)} already here
          {teachers ? ' and keep what they teach; the sheet adds to it.' : ' and will be updated.'}
        </p>
      )}

      {preview.checks.length > 0 && (
        <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-amber-900">
          <p className="font-medium">Worth checking</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {preview.checks.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <p className="mt-1">Import anyway, or fix the sheet and read it again.</p>
        </div>
      )}

      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-3 font-medium">Name</th>
              {teachers ? (
                <>
                  <th className="py-1 pr-3 font-medium">Subjects</th>
                  <th className="py-1 pr-3 font-medium">Classes</th>
                  <th className="py-1 font-medium">Periods a week</th>
                </>
              ) : (
                <th className="py-1 font-medium">Room type</th>
              )}
            </tr>
          </thead>
          <tbody>
            {shown.map(({ row, i, notes: n }) => (
              <tr key={i} className={`border-t border-slate-100 align-top ${n.length ? 'bg-amber-50' : ''}`}>
                <td className="py-1 pr-3 text-slate-800">
                  {row.name}
                  {n.map((note) => (
                    <div key={note} className="text-amber-800">{note}</div>
                  ))}
                </td>
                {teachers ? (
                  <>
                    <td className="py-1 pr-3">{(row.qualified_subjects || '').split(';').filter(Boolean).join(', ') || '\u2014'}</td>
                    <td className="py-1 pr-3">{(row.qualified_grades || '').split(';').filter(Boolean).join(', ') || 'All'}</td>
                    <td className="py-1">{row.max_periods_per_week || '\u2014'}</td>
                  </>
                ) : (
                  <td className="py-1">{row.required_room_type || '\u2014'}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {hidden > 0 && <p className="mt-1 text-slate-500">and {plural(hidden, 'more row')}.</p>}
      </div>

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onImport}
          disabled={saving || preview.total === 0}
          className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
        >
          {saving ? 'Importing…' : `Import ${plural(preview.total, what)}`}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-md border border-slate-300 px-3.5 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
    </section>
  )
}
