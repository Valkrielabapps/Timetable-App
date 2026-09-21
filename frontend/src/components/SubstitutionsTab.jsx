import { useEffect, useState, useMemo } from 'react'
import { api } from '../api'

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function SubstitutionsTab({ schoolId, teachers, classGroups }) {
  const [periods, setPeriods] = useState([])
  const [timetable, setTimetable] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  const [selectedDay, setSelectedDay] = useState(0) // 0 for Monday
  const [absentTeacherIds, setAbsentTeacherIds] = useState([])
  
  // substitutions: record of { entryId: substituteTeacherId }
  const [substitutions, setSubstitutions] = useState({})
  const [logs, setLogs] = useState([])
  
  const [view, setView] = useState('new') // 'new' | 'history'

  useEffect(() => {
    async function loadData() {
      setLoading(true)
      try {
        const [periodsData, timetablesData, logsData] = await Promise.all([
          api.listPeriods(schoolId),
          api.listTimetables(schoolId),
          api.listSubstitutionLogs(schoolId)
        ])
        setPeriods(periodsData)
        setLogs(logsData)
        
        // Find the active timetable (first one that is draft or published)
        const active = timetablesData.find(t => t.status === 'draft' || t.status === 'published')
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

  const toggleAbsentTeacher = (teacherId) => {
    setAbsentTeacherIds(prev => 
      prev.includes(teacherId) 
        ? prev.filter(id => id !== teacherId)
        : [...prev, teacherId]
    )
    // Clear substitutions that are no longer needed
    setSubstitutions({})
  }

  const handleSubstituteChange = (entryId, teacherId) => {
    setSubstitutions(prev => ({
      ...prev,
      [entryId]: teacherId
    }))
  }

  // Derived state: empty slots
  const emptySlots = useMemo(() => {
    if (!timetable || absentTeacherIds.length === 0) return []

    // Find all entries for the selected day where the assigned teacher is absent
    const entries = timetable.entries.filter(e => {
      const period = periods.find(p => p.id === e.period_id)
      return period && period.day_of_week === selectedDay && absentTeacherIds.includes(e.teacher_id)
    })

    // Sort by period order
    return entries.sort((a, b) => {
      const pA = periods.find(p => p.id === a.period_id)
      const pB = periods.find(p => p.id === b.period_id)
      return (pA?.order ?? 0) - (pB?.order ?? 0)
    })
  }, [timetable, absentTeacherIds, selectedDay, periods])

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

  // Ranked substitute candidates for one empty slot: teachers who are
  // qualified for the subject AND free at that period are "suggested"
  // (auto-filled below); everyone else who's merely free is a fallback so
  // the admin is never blocked when no qualified teacher happens to be
  // free. Excludes:
  //   - the absent teacher(s) themselves
  //   - anyone already teaching another class at that period (busy)
  //   - anyone marked unavailable for that period (Teacher.unavailable_period_ids
  //     — previously not checked here at all, so a teacher could get
  //     suggested for a slot they'd explicitly been marked out for)
  //   - anyone already staged as a substitute for a *different* slot at
  //     the same period in this same draft, so two simultaneous gaps don't
  //     both get assigned the same substitute
  // Takes the staged-substitutions map as a parameter (rather than always
  // reading the `substitutions` state directly) so the auto-fill pass
  // below can dedupe against picks it just made earlier in the same pass,
  // not just picks saved from a previous render.
  const rankTeachers = (entry, stagedMap) => {
    if (!timetable) return { suggested: [], others: [] }

    const busyTeacherIds = new Set(
      timetable.entries
        .filter(e => e.period_id === entry.period_id)
        .map(e => e.teacher_id)
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

    const free = teachers.filter(t =>
      !busyTeacherIds.has(t.id) &&
      !absentTeacherIds.includes(t.id) &&
      !(t.unavailable_period_ids || []).includes(entry.period_id) &&
      !alreadyStagedThisPeriod.has(t.id)
    )

    const byLightestLoad = (a, b) => (loadByTeacherId.get(a.id) || 0) - (loadByTeacherId.get(b.id) || 0)

    const suggested = free
      .filter(t => (t.qualified_subject_ids || []).includes(entry.subject_id))
      .sort(byLightestLoad)
    const suggestedIds = new Set(suggested.map(t => t.id))
    const others = free.filter(t => !suggestedIds.has(t.id)).sort(byLightestLoad)

    return { suggested, others }
  }

  const getRankedTeachers = (entry) => rankTeachers(entry, substitutions)

  // Auto-fill each empty slot with its top suggested candidate (qualified
  // + free + lightest-loaded) as soon as it appears, so the admin starts
  // from a sensible default instead of a blank picker — this is what
  // actually saves the "who can even teach Math right now" lookup by
  // hand. Only fills slots that don't already have a choice, so it never
  // clobbers a manual pick, and only fires when the slot has no
  // substitute yet (not on every keystroke/render). Fills slots in period
  // order and re-ranks against `next` (not the outer `substitutions`
  // state) on every iteration, so two simultaneous gaps at the same
  // period never both land on the same suggested substitute.
  useEffect(() => {
    setSubstitutions(prev => {
      let changed = false
      const next = { ...prev }
      for (const entry of emptySlots) {
        if (next[entry.id]) continue
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

  const saveSubstitutions = async () => {
    if (Object.keys(substitutions).length === 0) return
    
    const changes = Object.entries(substitutions).map(([entryId, subTeacherId]) => {
      const entry = emptySlots.find(e => e.id === parseInt(entryId))
      return {
        period_id: entry.period_id,
        absent_teacher_id: entry.teacher_id,
        substituting_teacher_id: parseInt(subTeacherId),
        class_group_id: entry.class_group_id,
        subject_id: entry.subject_id
      }
    })
    
    try {
      const newLog = await api.saveSubstitutionLog(schoolId, {
        day_of_week: selectedDay,
        changes
      })
      setLogs([newLog, ...logs])
      setAbsentTeacherIds([])
      setSubstitutions({})
      alert('Substitutions saved successfully!')
    } catch (err) {
      setError(err.message)
    }
  }

  if (loading) return <div className="p-8 text-gray-500">Loading data...</div>
  if (error) return <div className="p-8 text-red-600">{error}</div>
  if (!timetable) return <div className="p-8 text-gray-500">No active timetable found. Please generate a timetable first.</div>

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Substitutions</h2>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setView('new')}
            className={`px-4 py-2 rounded font-medium transition-colors ${
              view === 'new' ? 'bg-neutral-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            New Substitutions
          </button>
          <button
            onClick={() => setView('history')}
            className={`px-4 py-2 rounded font-medium transition-colors ${
              view === 'history' ? 'bg-neutral-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            History
          </button>
        </div>
      </div>

      {view === 'new' ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Left Column: Day & Absent Teachers */}
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">1. Select Day</h3>
              <select
                value={selectedDay}
                onChange={(e) => {
                  setSelectedDay(parseInt(e.target.value))
                  setAbsentTeacherIds([])
                  setSubstitutions({})
                }}
                className="w-full rounded border-gray-300 shadow-sm focus:border-neutral-900 focus:ring-neutral-900"
              >
                {DAY_NAMES.map((name, idx) => (
                  <option key={idx} value={idx}>{name}</option>
                ))}
              </select>
            </div>

            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">2. Absent Teachers</h3>
              {teachers.length === 0 ? (
                <p className="text-gray-500 text-sm">No teachers available.</p>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2">
                  {teachers.map(t => (
                    <label key={t.id} className="flex items-center gap-3 p-2 rounded hover:bg-gray-50 cursor-pointer transition-colors">
                      <input
                        type="checkbox"
                        checked={absentTeacherIds.includes(t.id)}
                        onChange={() => toggleAbsentTeacher(t.id)}
                        className="rounded border-gray-300 text-neutral-900 focus:ring-neutral-900 h-4 w-4"
                      />
                      <span className="text-gray-700">{t.name}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Empty Slots & Assignment */}
          <div className="md:col-span-2">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 h-full">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-gray-800">3. Assign Substitutes</h3>
                {emptySlots.length > 0 && (
                  <button
                    onClick={saveSubstitutions}
                    className="bg-neutral-900 text-white px-4 py-2 rounded shadow-sm hover:bg-neutral-700 font-medium transition-colors"
                  >
                    Save & View Summary
                  </button>
                )}
              </div>

              {absentTeacherIds.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <p>Select absent teachers to see empty slots.</p>
                </div>
              ) : emptySlots.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <p>No classes scheduled for the selected absent teachers on {DAY_NAMES[selectedDay]}.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {emptySlots.map(entry => {
                    const period = periods.find(p => p.id === entry.period_id)
                    const classGroup = classGroups.find(c => c.id === entry.class_group_id)
                    const absentTeacher = teachers.find(t => t.id === entry.teacher_id)
                    const { suggested, others } = getRankedTeachers(entry)
                    const currentPick = substitutions[entry.id]
                    const pickIsSuggested = currentPick && suggested.some(t => String(t.id) === String(currentPick))

                    return (
                      <div key={entry.id} className="p-4 border border-gray-200 rounded-lg bg-gray-50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                          <div className="font-semibold text-gray-900">{classGroup?.grade} {classGroup?.name}</div>
                          <div className="text-sm text-gray-600">
                            {period?.label || `Period ${period?.order}`} • Absent: {absentTeacher?.name}
                          </div>
                        </div>
                        <div className="min-w-[220px]">
                          <select
                            value={currentPick || ''}
                            onChange={(e) => handleSubstituteChange(entry.id, e.target.value)}
                            className="w-full rounded border-gray-300 shadow-sm focus:border-neutral-900 focus:ring-neutral-900"
                          >
                            <option value="">-- Assign Substitute --</option>
                            {suggested.length > 0 && (
                              <optgroup label="Suggested (qualified & free)">
                                {suggested.map(t => (
                                  <option key={t.id} value={t.id}>{t.name}</option>
                                ))}
                              </optgroup>
                            )}
                            {others.length > 0 && (
                              <optgroup label="Other available teachers">
                                {others.map(t => (
                                  <option key={t.id} value={t.id}>{t.name}</option>
                                ))}
                              </optgroup>
                            )}
                          </select>
                          {currentPick && (
                            <p className={`mt-1 text-xs ${pickIsSuggested ? 'text-emerald-600' : 'text-amber-600'}`}>
                              {pickIsSuggested
                                ? 'Suggested — qualified for this subject and free at this period'
                                : 'Not qualified for this subject — pick a suggested teacher above if one is free'}
                            </p>
                          )}
                          {suggested.length === 0 && others.length === 0 && (
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
          {logs.length === 0 ? (
            <p className="text-gray-500">No substitutions recorded yet.</p>
          ) : (
            <div className="space-y-8">
              {logs.map(log => (
                <div key={log.id} className="border-b border-gray-100 pb-8 last:border-0 last:pb-0">
                  <div className="flex items-center justify-between mb-4">
                    <h4 className="font-medium text-gray-900">
                      {DAY_NAMES[log.day_of_week]} • {new Date(log.created_at).toLocaleString()}
                    </h4>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {log.changes.map((change, idx) => {
                      const period = periods.find(p => p.id === change.period_id)
                      const classGroup = classGroups.find(c => c.id === change.class_group_id)
                      const absent = teachers.find(t => t.id === change.absent_teacher_id)
                      const sub = teachers.find(t => t.id === change.substituting_teacher_id)
                      
                      return (
                        <div key={idx} className="bg-gray-50 p-3 rounded border border-gray-200 text-sm">
                          <div className="font-semibold text-neutral-700">{classGroup?.grade} {classGroup?.name}</div>
                          <div className="text-gray-600 mb-2">{period?.label || `Period ${period?.order}`}</div>
                          <div className="flex items-center gap-2">
                            <span className="text-red-600 line-through truncate" title={absent?.name}>{absent?.name}</span>
                            <span className="text-gray-400">→</span>
                            <span className="text-green-600 font-medium truncate" title={sub?.name}>{sub?.name}</span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
