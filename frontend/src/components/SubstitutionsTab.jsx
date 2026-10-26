import { useEffect, useState, useMemo } from 'react'
import { api } from '../api'
import SearchableSelect from './SearchableSelect'
import SubstitutionSummary from './SubstitutionSummary'
import { compareNames, loadChoice, rankMatches, saveChoice } from '../sorting'
import {
  CATEGORIES, WHOLE_SCHOOL, categoryLabel, formatDate, todayIso, weekdayOf,
} from '../substitutionSummary'
import { pickVersions } from '../lib/versions'

/**
 * Arranging cover for the teachers who are away on a given date.
 *
 *   1. The date.
 *   2. Which part of the school - pre-primary, primary, middle, high school,
 *      or the whole school. Parts often have their own building, so cover is
 *      arranged a part at a time; which grades are in which part is set in
 *      Settings > School categories.
 *   3. Who is away: only teachers with lessons in that part that day are
 *      listed. Each is away the whole day, or for the periods ticked.
 *   4. A substitute for each of their lessons. Suggestions are free at that
 *      period and qualified for the subject, from the same part of the school
 *      first; teachers from other parts are listed below them. A lesson left
 *      without one is saved as not covered, so the summary says so.
 *
 * Saving shows the day's summary, to print, download or copy for WhatsApp.
 * Saving the same date and part again replaces what was saved before.
 */

const periodName = (p) =>
  // Periods are stored from zero and shown from one.
  p?.number != null ? `Period ${p.number}` : p?.label || `Period ${(p?.order ?? 0) + 1}`

const logDate = (log) => log.date ?? log.created_at.slice(0, 10)
const logCategory = (log) => log.category ?? WHOLE_SCHOOL
const lessonKey = (periodId, classGroupId, teacherId) => `${periodId}:${classGroupId}:${teacherId}`

export default function SubstitutionsTab({ schoolId, teachers, classGroups, readOnly = false }) {
  const [periods, setPeriods] = useState([])
  const [timetable, setTimetable] = useState(null)
  const [gradeCategories, setGradeCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [date, setDate] = useState(todayIso)
  const categoryKey = `substitutions-category-${schoolId}`
  const [category, setCategory] = useState(() => loadChoice(categoryKey, null))
  // teacherId -> null (away all day) or [periodId, ...] (away those periods)
  const [absences, setAbsences] = useState({})
  const [absentSearch, setAbsentSearch] = useState('')

  // entryId -> substitute's id as a string; '' = chosen to leave uncovered
  const [substitutions, setSubstitutions] = useState({})
  const [logs, setLogs] = useState([])
  const [summary, setSummary] = useState(null)
  const [saving, setSaving] = useState(false)

  const [view, setView] = useState('new') // 'new' | 'summary' | 'history'

  useEffect(() => {
    async function loadData() {
      setLoading(true)
      try {
        const [periodsData, timetablesData, logsData, categoriesData] = await Promise.all([
          api.listPeriods(schoolId),
          api.listTimetables(schoolId),
          api.listSubstitutionLogs(schoolId),
          api.getGradeCategories(schoolId),
        ])
        setPeriods(periodsData)
        setLogs(logsData)
        setGradeCategories(categoriesData)

        // The newest usable timetable - the one the Timetable tab shows.
        // Every generation adds a draft and the list comes back unordered, so
        // taking the first match used to cover absences against an old one.
        // Ids are assigned in creation order, so the highest is the newest.
        // The version the school works from - the one the Timetable tab shows.
        const active = pickVersions(timetablesData).current
        if (active) {
          const tt = await api.getTimetable(active.id)
          setTimetable(tt)
        }
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [schoolId])

  const weekday = date ? weekdayOf(date) : null
  const periodById = useMemo(() => new Map(periods.map(p => [p.id, p])), [periods])

  // Which part of the school each lesson is in, by its section's grade.
  const categoryOfGrade = useMemo(
    () => new Map(gradeCategories.map(g => [g.grade, g.category])),
    [gradeCategories],
  )
  const categoryOfSection = useMemo(
    () => new Map(classGroups.map(c => [c.id, categoryOfGrade.get(c.grade) ?? null])),
    [classGroups, categoryOfGrade],
  )
  const inScope = (entry) => category === WHOLE_SCHOOL || categoryOfSection.get(entry.class_group_id) === category

  // The chosen day's lessons in the chosen part, in period order.
  const dayLessons = useMemo(() => {
    if (!timetable || weekday == null || !category) return []
    return timetable.entries
      .filter(e => e.teacher_id != null && periodById.get(e.period_id)?.day_of_week === weekday && inScope(e))
      .sort((a, b) => (periodById.get(a.period_id)?.order ?? 0) - (periodById.get(b.period_id)?.order ?? 0))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timetable, weekday, category, periodById, categoryOfSection])

  // The parts of the school each teacher works in, over the whole week - the
  // building they're usually in.
  const teacherCategories = useMemo(() => {
    const out = new Map()
    for (const e of timetable?.entries ?? []) {
      if (e.teacher_id == null) continue
      if (!out.has(e.teacher_id)) out.set(e.teacher_id, new Set())
      out.get(e.teacher_id).add(categoryOfSection.get(e.class_group_id) ?? null)
    }
    return out
  }, [timetable, categoryOfSection])

  // Teachers with lessons here that day, and the periods of those lessons.
  const lessonPeriodsByTeacher = useMemo(() => {
    const out = new Map()
    for (const e of dayLessons) {
      if (!out.has(e.teacher_id)) out.set(e.teacher_id, [])
      const list = out.get(e.teacher_id)
      if (!list.includes(e.period_id)) list.push(e.period_id)
    }
    return out
  }, [dayLessons])
  const teachersWithLessons = teachers.filter(t => lessonPeriodsByTeacher.has(t.id))

  const isAway = (teacherId, periodId) => {
    if (!(teacherId in absences)) return false
    const ids = absences[teacherId]
    return ids == null || ids.includes(periodId)
  }

  // What's already saved for this date in other parts of the school: those
  // substitutes are taken at those periods, and those absent teachers are away.
  const savedElsewhere = useMemo(() => {
    const taken = new Set()
    const away = new Map()
    for (const log of logs) {
      if (logDate(log) !== date || logCategory(log) === category) continue
      for (const c of log.changes) {
        if (c.substituting_teacher_id != null) taken.add(`${c.period_id}:${c.substituting_teacher_id}`)
      }
      for (const a of log.absences ?? []) {
        if (a.period_ids == null) away.set(a.teacher_id, null)
        else if (away.get(a.teacher_id) !== null) {
          away.set(a.teacher_id, [...(away.get(a.teacher_id) ?? []), ...a.period_ids])
        }
      }
    }
    return { taken, away }
  }, [logs, date, category])

  const savedHere = logs.find(log => logDate(log) === date && logCategory(log) === category)

  // Choosing a date and part that already has saved cover starts from it,
  // so changing one substitute doesn't mean entering the rest again.
  useEffect(() => {
    if (!savedHere || !timetable) {
      setAbsences({})
      setSubstitutions({})
      return
    }
    const saved = {}
    for (const a of savedHere.absences ?? []) saved[a.teacher_id] = a.period_ids ?? null
    // Older records kept only the lessons covered.
    if (!savedHere.absences?.length) {
      for (const c of savedHere.changes) {
        saved[c.absent_teacher_id] = [...(saved[c.absent_teacher_id] ?? []), c.period_id]
      }
    }
    const picks = new Map(savedHere.changes.map(c => [
      lessonKey(c.period_id, c.class_group_id, c.absent_teacher_id),
      c.substituting_teacher_id == null ? '' : String(c.substituting_teacher_id),
    ]))
    const subs = {}
    for (const e of timetable.entries) {
      const pick = picks.get(lessonKey(e.period_id, e.class_group_id, e.teacher_id))
      if (pick !== undefined) subs[e.id] = pick
    }
    setAbsences(saved)
    setSubstitutions(subs)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, category, timetable, savedHere?.id])

  const chooseCategory = (key) => {
    setCategory(key)
    saveChoice(categoryKey, key)
  }

  const toggleAbsentTeacher = (teacherId) => {
    setAbsences(prev => {
      const next = { ...prev }
      if (teacherId in next) delete next[teacherId]
      else next[teacherId] = null
      return next
    })
  }
  const setWholeDay = (teacherId, wholeDay) => {
    setAbsences(prev => ({ ...prev, [teacherId]: wholeDay ? null : [] }))
  }
  const togglePeriod = (teacherId, periodId) => {
    setAbsences(prev => {
      const ids = prev[teacherId] ?? []
      return {
        ...prev,
        [teacherId]: ids.includes(periodId) ? ids.filter(id => id !== periodId) : [...ids, periodId],
      }
    })
  }

  // The lessons that need cover.
  const emptySlots = useMemo(
    () => dayLessons.filter(e => isAway(e.teacher_id, e.period_id)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [dayLessons, absences],
  )

  // How many periods/week each teacher is already carrying on the live
  // timetable — used to break ties among equally-qualified substitutes by
  // preferring whoever's lighter-loaded, rather than an arbitrary order.
  const loadByTeacherId = useMemo(() => {
    const counts = new Map()
    if (timetable) {
      for (const e of timetable.entries) {
        counts.set(e.teacher_id, (counts.get(e.teacher_id) || 0) + 1)
      }
    }
    return counts
  }, [timetable])

  // Ranked substitute candidates for one lesson. Only teachers free at that
  // period count; excluded are:
  //   - anyone away at that period (here, or as saved for another part)
  //   - anyone already teaching another class at that period (busy)
  //   - anyone marked unavailable for that period (Teacher.unavailable_period_ids)
  //   - anyone already picked for a *different* lesson at the same period,
  //     here or in another part's saved cover for this date
  // Of the rest, three groups, each lightest-loaded first:
  //   suggested  qualified for the subject, working in the lesson's part
  //   same       working in the lesson's part, not qualified
  //   elsewhere  everyone else free - other buildings, so listed last
  // Takes the staged-substitutions map as a parameter (rather than always
  // reading the `substitutions` state directly) so the auto-fill pass
  // below can dedupe against picks it just made earlier in the same pass.
  const rankTeachers = (entry, stagedMap) => {
    if (!timetable) return { suggested: [], same: [], elsewhere: [] }

    const busyTeacherIds = new Set(
      timetable.entries.filter(e => e.period_id === entry.period_id).map(e => e.teacher_id)
    )
    const alreadyStagedThisPeriod = new Set(
      Object.entries(stagedMap)
        .filter(([entryId, subTeacherId]) => {
          if (parseInt(entryId) === entry.id || !subTeacherId) return false
          const other = emptySlots.find(e => e.id === parseInt(entryId))
          return other && other.period_id === entry.period_id
        })
        .map(([, subTeacherId]) => parseInt(subTeacherId))
    )
    const awayElsewhere = (t) => {
      if (!savedElsewhere.away.has(t.id)) return false
      const ids = savedElsewhere.away.get(t.id)
      return ids == null || ids.includes(entry.period_id)
    }

    const free = teachers.filter(t =>
      !busyTeacherIds.has(t.id) &&
      !isAway(t.id, entry.period_id) &&
      !awayElsewhere(t) &&
      !(t.unavailable_period_ids || []).includes(entry.period_id) &&
      !alreadyStagedThisPeriod.has(t.id) &&
      !savedElsewhere.taken.has(`${entry.period_id}:${t.id}`)
    )

    const byLightestLoad = (a, b) =>
      (loadByTeacherId.get(a.id) || 0) - (loadByTeacherId.get(b.id) || 0) || compareNames(a.name, b.name)
    const lessonCategory = categoryOfSection.get(entry.class_group_id) ?? null
    const worksHere = (t) => teacherCategories.get(t.id)?.has(lessonCategory) ?? false
    const qualified = (t) => (t.qualified_subject_ids || []).includes(entry.subject_id)

    return {
      suggested: free.filter(t => worksHere(t) && qualified(t)).sort(byLightestLoad),
      same: free.filter(t => worksHere(t) && !qualified(t)).sort(byLightestLoad),
      elsewhere: free.filter(t => !worksHere(t)).sort(byLightestLoad),
    }
  }

  // Auto-fill each lesson with its top suggestion as soon as it needs
  // cover, so the admin starts from a sensible default instead of a blank
  // picker. Only fills lessons with no choice yet (a manual pick, or a
  // choice to leave it uncovered, is kept). Fills in period order and
  // re-ranks against `next` on every iteration, so two lessons at the same
  // period never both land on the same substitute.
  useEffect(() => {
    setSubstitutions(prev => {
      let changed = false
      const next = { ...prev }
      for (const entry of emptySlots) {
        if (next[entry.id] !== undefined) continue
        const { suggested } = rankTeachers(entry, next)
        if (suggested.length > 0) {
          next[entry.id] = String(suggested[0].id)
          changed = true
        }
      }
      return changed ? next : prev
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emptySlots])

  const showSummary = async (forDate, forCategory) => {
    const s = await api.getSubstitutionSummary(
      schoolId, forDate, forCategory === WHOLE_SCHOOL ? null : forCategory,
    )
    setSummary(s)
    setView('summary')
  }

  const saveSubstitutions = async () => {
    const changes = emptySlots.map(entry => {
      const pick = substitutions[entry.id]
      return {
        period_id: entry.period_id,
        absent_teacher_id: entry.teacher_id,
        substituting_teacher_id: pick ? parseInt(pick) : null,
        class_group_id: entry.class_group_id,
        subject_id: entry.subject_id,
      }
    })
    setSaving(true)
    try {
      const saved = await api.saveSubstitutionLog(schoolId, {
        date,
        category: category === WHOLE_SCHOOL ? null : category,
        absences: Object.entries(absences).map(([teacherId, ids]) => ({
          teacher_id: parseInt(teacherId),
          period_ids: ids == null ? null : ids,
        })),
        changes,
      })
      setLogs(prev => [saved, ...prev.filter(log => log.id !== saved.id)])
      await showSummary(date, category)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // History: one row per date, newest first, with the parts saved for it.
  const history = useMemo(() => {
    const byDate = new Map()
    for (const log of logs) {
      const d = logDate(log)
      if (!byDate.has(d)) byDate.set(d, [])
      byDate.get(d).push(log)
    }
    return [...byDate.entries()].sort(([a], [b]) => (a < b ? 1 : -1))
  }, [logs])

  if (loading) return <div className="p-8 text-gray-500">Loading data...</div>
  if (error) return <div className="p-8 text-red-600">{error}</div>
  if (!timetable) return <div className="p-8 text-gray-500">No active timetable found. Please generate a timetable first.</div>

  const partsChoice = [{ key: WHOLE_SCHOOL, label: 'Whole school' }, ...CATEGORIES]
  const tabButton = (id, label) => (
    <button
      onClick={() => setView(id)}
      className={`px-4 py-2 rounded font-medium transition-colors ${
        view === id ? 'bg-neutral-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
      }`}
    >
      {label}
    </button>
  )
  const uncoveredCount = emptySlots.filter(e => !substitutions[e.id]).length

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Substitutions</h2>
        <div className="flex flex-wrap gap-2">
          {tabButton('new', 'New Substitutions')}
          {summary && tabButton('summary', 'Summary')}
          {tabButton('history', 'History')}
        </div>
      </div>

      {view === 'summary' && summary ? (
        <SubstitutionSummary schoolId={schoolId} summary={summary} />
      ) : view === 'new' ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">1. Date</h3>
              <input
                type="date"
                aria-label="Date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-2.5 py-1.5"
              />
              {date && <p className="mt-2 text-sm text-gray-500">{formatDate(date)}</p>}
            </div>

            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-1">2. Which part of the school?</h3>
              <p className="mb-3 text-xs text-gray-500">Grades are grouped in Settings &gt; School categories.</p>
              <div role="radiogroup" aria-label="Part of the school" className="flex flex-wrap gap-2">
                {partsChoice.map(c => (
                  <button
                    key={c.key}
                    role="radio"
                    aria-checked={category === c.key}
                    onClick={() => chooseCategory(c.key)}
                    className={`rounded-full border px-3 py-1 text-sm ${
                      category === c.key
                        ? 'border-neutral-900 bg-neutral-900 text-white'
                        : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            </div>

            {category && date && (
              <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-800 mb-1">3. Absent Teachers</h3>
                <p className="mb-3 text-xs text-gray-500">
                  Teachers with lessons in {categoryLabel(category).toLowerCase()} on {formatDate(date).split(',')[0]}.
                </p>
                {teachersWithLessons.length === 0 ? (
                  <p className="text-gray-500 text-sm">Nobody has lessons here that day.</p>
                ) : (
                  <div className="space-y-2">
                    <input
                      type="search"
                      aria-label="Search teachers"
                      value={absentSearch}
                      onChange={(e) => setAbsentSearch(e.target.value)}
                      placeholder="Search teachers"
                      className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-neutral-900 focus:outline-none"
                    />
                    <div className="space-y-1 max-h-[400px] overflow-y-auto pr-2">
                      {/* Alphabetical, titles ignored; narrowed by the search. */}
                      {rankMatches(teachersWithLessons, absentSearch).map(t => {
                        const away = t.id in absences
                        const ids = absences[t.id]
                        return (
                          <div key={t.id} className="rounded p-2 hover:bg-gray-50">
                            <label className="flex items-center gap-3 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={away}
                                disabled={readOnly}
                                onChange={() => toggleAbsentTeacher(t.id)}
                                className="rounded border-gray-300 text-neutral-900 focus:ring-neutral-900 h-4 w-4"
                              />
                              <span className="text-gray-700">{t.name}</span>
                            </label>
                            {away && (
                              <div className="ml-7 mt-2 space-y-2 text-sm">
                                <div role="radiogroup" aria-label={`How long ${t.name} is away`} className="flex gap-3">
                                  <label className="flex items-center gap-1.5">
                                    <input type="radio" checked={ids == null} disabled={readOnly}
                                      onChange={() => setWholeDay(t.id, true)} />
                                    Whole day
                                  </label>
                                  <label className="flex items-center gap-1.5">
                                    <input type="radio" checked={ids != null} disabled={readOnly}
                                      onChange={() => setWholeDay(t.id, false)} />
                                    Some periods
                                  </label>
                                </div>
                                {ids != null && (
                                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                                    {lessonPeriodsByTeacher.get(t.id).map(pid => (
                                      <label key={pid} className="flex items-center gap-1.5">
                                        <input
                                          type="checkbox"
                                          aria-label={`${t.name} away ${periodName(periodById.get(pid))}`}
                                          checked={ids.includes(pid)}
                                          disabled={readOnly}
                                          onChange={() => togglePeriod(t.id, pid)}
                                        />
                                        {periodName(periodById.get(pid))}
                                      </label>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="md:col-span-2">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 h-full">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
                <div>
                  <h3 className="text-lg font-semibold text-gray-800">4. Assign Substitutes</h3>
                  {savedHere && (
                    <p className="text-xs text-gray-500">Saved earlier for this date — saving again replaces it.</p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {savedHere && (
                    <button
                      onClick={() => showSummary(date, category)}
                      className="rounded border border-gray-300 px-4 py-2 font-medium hover:bg-gray-50"
                    >
                      View summary
                    </button>
                  )}
                  {!readOnly && emptySlots.length > 0 && (
                    <button
                      onClick={saveSubstitutions}
                      disabled={saving}
                      className="bg-neutral-900 text-white px-4 py-2 rounded shadow-sm hover:bg-neutral-700 font-medium transition-colors disabled:opacity-60"
                    >
                      Save & View Summary
                    </button>
                  )}
                </div>
              </div>

              {!category ? (
                <div className="text-center py-12 text-gray-500">
                  <p>Choose which part of the school to arrange cover for.</p>
                </div>
              ) : Object.keys(absences).length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <p>Select absent teachers to see their lessons.</p>
                </div>
              ) : emptySlots.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <p>No lessons need cover for the periods chosen.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {uncoveredCount > 0 && (
                    <p className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
                      {uncoveredCount} lesson{uncoveredCount === 1 ? '' : 's'} without a substitute will be saved as not covered.
                    </p>
                  )}
                  {emptySlots.map(entry => {
                    const period = periodById.get(entry.period_id)
                    const classGroup = classGroups.find(c => c.id === entry.class_group_id)
                    const absentTeacher = teachers.find(t => t.id === entry.teacher_id)
                    const { suggested, same, elsewhere } = rankTeachers(entry, substitutions)
                    const currentPick = substitutions[entry.id]
                    const pickIsSuggested = currentPick && suggested.some(t => String(t.id) === String(currentPick))
                    const part = categoryLabel(categoryOfSection.get(entry.class_group_id) ?? null)
                    const option = (group) => (t) => ({
                      value: t.id, label: t.name, group, hint: `${loadByTeacherId.get(t.id) || 0} periods`,
                    })

                    return (
                      <div
                        key={entry.id}
                        className={`p-4 border rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                          currentPick ? 'border-gray-200 bg-gray-50' : 'border-red-200 bg-red-50'
                        }`}
                      >
                        <div>
                          <div className="font-semibold text-gray-900">{classGroup?.grade} {classGroup?.name}</div>
                          <div className="text-sm text-gray-600">
                            {periodName(period)} • {entry.subject_name} • Absent: {absentTeacher?.name}
                          </div>
                          {/* In a block the rest of the section is in its other
                              options' lessons; the cover is for this group only. */}
                          {entry.elective_block_id != null && (
                            <div className="text-xs text-gray-500">
                              {entry.elective_block_name ?? 'Elective block'}: only the {entry.subject_name} group
                            </div>
                          )}
                        </div>
                        <div className="min-w-[220px]">
                          {/* Alphabetical within each group; each name shows its
                              load. The auto-filled pick is the lightest-loaded
                              suggestion. */}
                          <SearchableSelect
                            ariaLabel={`Substitute for ${entry.subject_name ?? 'this lesson'}, ${periodName(period)}, ${classGroup?.grade ?? ''} ${classGroup?.name ?? ''}`.trim()}
                            value={currentPick || null}
                            disabled={readOnly}
                            onChange={(id) => setSubstitutions(prev => ({
                              ...prev, [entry.id]: id == null ? '' : String(id),
                            }))}
                            emptyOption={{ label: 'Not covered' }}
                            options={[
                              ...suggested.map(option(`Suggested: qualified, free, in ${part}`)),
                              ...same.map(option(`Free in ${part}`)),
                              ...elsewhere.map(option('Free in other parts of the school')),
                            ]}
                            className="w-full"
                          />
                          {currentPick ? (
                            <p className={`mt-1 text-xs ${pickIsSuggested ? 'text-emerald-600' : 'text-amber-600'}`}>
                              {pickIsSuggested
                                ? 'Suggested: qualified for this subject, free, and in this part of the school'
                                : 'Not a suggestion: pick a suggested teacher above if one is free'}
                            </p>
                          ) : (
                            <p className="mt-1 text-xs font-medium text-red-700">Not covered</p>
                          )}
                          {suggested.length === 0 && same.length === 0 && elsewhere.length === 0 && (
                            <p className="mt-1 text-xs text-red-600">No free teachers found for this period.</p>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800 mb-6">Substitution History</h3>
          {history.length === 0 ? (
            <p className="text-gray-500">No substitutions recorded yet.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {history.map(([d, dayLogs]) => {
                const parts = [...new Set(dayLogs.map(logCategory))]
                const lessons = dayLogs.reduce((n, log) => n + log.changes.length, 0)
                const uncovered = dayLogs.reduce(
                  (n, log) => n + log.changes.filter(c => c.substituting_teacher_id == null).length, 0,
                )
                return (
                  <li key={d} className="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="font-medium text-gray-900">{formatDate(d)}</div>
                      <div className="text-sm text-gray-500">
                        {lessons} lesson{lessons === 1 ? '' : 's'} needed cover
                        {uncovered > 0 && <span className="text-red-600"> · {uncovered} not covered</span>}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {parts.length > 1 || parts[0] !== WHOLE_SCHOOL ? (
                        <button
                          onClick={() => showSummary(d, WHOLE_SCHOOL)}
                          className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
                        >
                          Whole school
                        </button>
                      ) : null}
                      {parts
                        .slice()
                        .sort((a, b) => partsChoice.findIndex(c => c.key === a) - partsChoice.findIndex(c => c.key === b))
                        .map(key => (
                          <button
                            key={key}
                            onClick={() => showSummary(d, key)}
                            className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
                          >
                            {categoryLabel(key)}
                          </button>
                        ))}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
