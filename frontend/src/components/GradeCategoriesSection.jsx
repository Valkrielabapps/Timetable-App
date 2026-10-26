import { useEffect, useState } from 'react'
import { api } from '../api'
import SearchableSelect from './SearchableSelect'
import { CATEGORIES, categoryLabel } from '../substitutionSummary'

/**
 * Settings > School categories: which part of the school each grade is in,
 * for arranging substitutions a block at a time.
 *
 * Every grade starts where its name puts it - Nursery/LKG/UKG pre-primary,
 * 1-5 primary, 6-8 middle, 9-12 high school - and can be moved. A grade
 * whose name doesn't say ("Foundation") has no part until one is chosen;
 * it still shows in whole-school substitutions.
 */
export default function GradeCategoriesSection({ schoolId, isAdmin }) {
  const [grades, setGrades] = useState(null)
  const [draft, setDraft] = useState({})
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let live = true
    api.getGradeCategories(schoolId)
      .then((rows) => {
        if (!live) return
        setGrades(rows)
        setDraft(Object.fromEntries(rows.map((g) => [g.grade, g.category])))
      })
      .catch((err) => live && setError(err.message))
    return () => {
      live = false
    }
  }, [schoolId])

  const changed = grades?.some((g) => draft[g.grade] !== g.category)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const rows = await api.saveGradeCategories(schoolId, draft)
      setGrades(rows)
      setDraft(Object.fromEntries(rows.map((g) => [g.grade, g.category])))
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h3 className="text-base font-semibold">School categories</h3>
      <p className="mt-1 text-sm text-slate-500">
        Which part of the school each grade is in. Substitutions can be arranged and shared a part at a time,
        and suggested substitutes come from the same part first.
      </p>
      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
      {grades == null ? (
        !error && <p className="mt-4 text-sm text-slate-500">Loading…</p>
      ) : grades.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">Add grades and sections first.</p>
      ) : (
        <>
          <table className="mt-5 w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">
                <th className="pb-2 font-medium">Grade</th>
                <th className="pb-2 font-medium">Part of the school</th>
              </tr>
            </thead>
            <tbody>
              {grades.map((g) => (
                <tr key={g.grade} className="border-t border-slate-100">
                  <td className="py-2 pr-4">{g.grade}</td>
                  <td className="py-2">
                    <div className="flex items-center gap-3">
                      <SearchableSelect
                        ariaLabel={`Part of the school for ${g.grade}`}
                        value={draft[g.grade]}
                        disabled={!isAdmin}
                        sort={false}
                        onChange={(value) => setDraft((prev) => ({ ...prev, [g.grade]: value }))}
                        emptyOption={{ label: 'None' }}
                        options={CATEGORIES.map((c) => ({ value: c.key, label: c.label }))}
                        className="w-48"
                      />
                      {draft[g.grade] !== g.default && (
                        <span className="text-xs text-slate-400">
                          Default: {g.default ? categoryLabel(g.default) : 'none'}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {isAdmin && (
            <div className="mt-5 flex items-center gap-3">
              <button
                onClick={save}
                disabled={!changed || saving}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Save
              </button>
              {saved && <span role="status" className="text-sm text-emerald-600">Saved</span>}
            </div>
          )}
        </>
      )}
    </section>
  )
}
