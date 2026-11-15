import { useEffect, useRef, useState } from 'react'
import { rankMatches } from '../sorting'

/**
 * Who may teach this subject in this section: any qualified teacher, one
 * fixed teacher, or two or more who share its periods between them
 * ("Shared: Priya, Joseph"). Used for normal subjects and for groups in an
 * elective block. Ticks are kept locally and saved once, on Done or a click
 * outside, so ticking three names is one request rather than three racing.
 */
export default function TeacherPicker({ subjectName, teachers, selectedIds, disabled, onChange }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(selectedIds)
  const [search, setSearch] = useState('')
  const ref = useRef(null)
  const selectedKey = selectedIds.join(',')
  // Alphabetical, titles ignored; narrowed by what's typed.
  const shown = rankMatches(teachers, search)

  useEffect(() => {
    if (!open) setDraft(selectedIds)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey, open])

  function close(save) {
    setOpen(false)
    setSearch('')
    const changed = draft.slice().sort().join(',') !== selectedIds.slice().sort().join(',')
    if (save && changed) onChange(draft)
  }

  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && close(true)
    const onKey = (e) => e.key === 'Escape' && close(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  })

  const nameOf = (id) => teachers.find((t) => t.id === id)?.name ?? 'Unknown teacher'
  const label =
    selectedIds.length === 0
      ? 'Any (let solver choose)'
      : selectedIds.length === 1
        ? nameOf(selectedIds[0])
        : `Shared: ${selectedIds.map(nameOf).join(', ')}`

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => (open ? close(true) : setOpen(true))}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`Teachers for ${subjectName}: ${label}`}
        title="Who teaches this here. Pick one to fix the teacher, or several to share its periods between them."
        className="flex max-w-[220px] items-center gap-1.5 rounded border border-neutral-200 bg-neutral-100/40 px-1.5 py-1 text-left text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-60"
      >
        <span className="truncate">{label}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="flex-none text-neutral-500" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div role="dialog" aria-label={`Choose teachers for ${subjectName}`} className="absolute left-0 top-full z-30 mt-1 w-64 rounded-lg border border-neutral-200 bg-white p-2 shadow-lg">
          <p className="px-2 pb-1.5 pt-1 text-[11px] leading-snug text-neutral-500">
            Tick one to fix the teacher, or several to share the periods between them.
          </p>
          <input
            autoFocus
            aria-label={`Search teachers for ${subjectName}`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              // Enter ticks (or unticks) the best match, so a name can be
              // typed and chosen without reaching for the mouse.
              if (e.key === 'Enter' && shown[0]) {
                e.preventDefault()
                const t = shown[0]
                setDraft((d) => (d.includes(t.id) ? d.filter((x) => x !== t.id) : [...d, t.id]))
                setSearch('')
              }
            }}
            placeholder="Type to search"
            className="mb-1 w-full rounded border border-neutral-200 px-2 py-1 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <ul className="max-h-56 overflow-y-auto">
            {shown.length === 0 && <li className="px-2 py-1.5 text-xs text-neutral-400">No matches</li>}
            {shown.map((t) => (
              <li key={t.id}>
                <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-neutral-800 hover:bg-neutral-50">
                  <input
                    type="checkbox"
                    checked={draft.includes(t.id)}
                    onChange={() =>
                      setDraft((d) => (d.includes(t.id) ? d.filter((x) => x !== t.id) : [...d, t.id]))
                    }
                    className="h-4 w-4 rounded border-neutral-300"
                  />
                  {t.name}
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-1.5 flex items-center justify-between border-t border-neutral-100 px-2 pt-2">
            <button
              type="button"
              onClick={() => setDraft([])}
              className="text-xs font-medium text-neutral-500 hover:text-neutral-800"
            >
              Clear (any teacher)
            </button>
            <button
              type="button"
              onClick={() => close(true)}
              className="rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white hover:bg-neutral-700"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
