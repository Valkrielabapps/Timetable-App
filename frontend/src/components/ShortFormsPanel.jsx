import { useEffect, useState } from 'react'
import { api } from '../api'

/**
 * The short forms this school has confirmed ("MAT" is Mathematics, "BEAUL"
 * is Beula Rao). Every import and the rules page read them, so the school is
 * asked about each one only once. A wrong one can be removed here, or one
 * added before an import asks. See backend/app/services/aliases.py.
 */
export default function ShortFormsPanel({ schoolId, kind }) {
  const [items, setItems] = useState(null)
  const [text, setText] = useState('')
  const [meaning, setMeaning] = useState('')
  const [error, setError] = useState(null)
  const word = kind === 'teacher' ? 'teacher' : 'subject'

  useEffect(() => {
    let live = true
    Promise.resolve().then(() => api.shortForms(schoolId)).then((r) => live && setItems(r?.items || [])).catch(() => live && setItems([]))
    return () => { live = false }
  }, [schoolId])

  async function add(e) {
    e.preventDefault()
    setError(null)
    try {
      const r = await api.addShortForm(schoolId, { kind, text: text.trim(), meaning: meaning.trim() })
      setItems(r.items)
      setText('')
      setMeaning('')
    } catch (err) {
      setError(err.message)
    }
  }

  async function remove(id) {
    setError(null)
    try {
      setItems((await api.deleteShortForm(schoolId, id)).items)
    } catch (err) {
      setError(err.message)
    }
  }

  if (items === null) return null
  const mine = items.filter((x) => x.kind === kind)
  return (
    <div className="mt-3 rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-medium">Short forms</h3>
      <p className="mt-1 text-xs text-slate-500">
        {kind === 'teacher'
          ? 'How your sheets shorten teachers’ names. Once you confirm one in an import, no import or rule asks about it again.'
          : 'Your school’s own short forms for subjects. Common ones like SST, EVS, SUPW and 2LN are already understood.'}
      </p>
      {mine.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-2">
          {mine.map((x) => (
            <li key={x.id} className="flex items-center gap-1 rounded-full border border-slate-200 px-2 py-0.5 text-xs">
              <span className="font-mono">{x.text}</span>
              <span className="text-slate-400">→</span>
              <span>{x.meaning}</span>
              <button
                type="button"
                onClick={() => remove(x.id)}
                aria-label={`Forget ${x.text}`}
                className="ml-1 text-slate-500 hover:text-red-600"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-slate-500">None yet.</p>
      )}
      <form onSubmit={add} className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <input
          aria-label="Short form"
          placeholder={kind === 'teacher' ? 'BEAUL' : 'S.Sc'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="w-24 rounded border border-slate-300 px-2 py-1"
        />
        <span className="text-slate-500">means</span>
        <input
          aria-label={`Full ${word} name`}
          placeholder={kind === 'teacher' ? 'Beula Rao' : 'Social Science'}
          value={meaning}
          onChange={(e) => setMeaning(e.target.value)}
          className="w-40 rounded border border-slate-300 px-2 py-1"
        />
        <button
          type="submit"
          disabled={!text.trim() || !meaning.trim()}
          className="rounded border border-slate-300 px-2 py-1 font-medium disabled:opacity-50"
        >
          Add
        </button>
      </form>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  )
}
