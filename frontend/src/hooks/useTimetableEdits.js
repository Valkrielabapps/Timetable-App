import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { api } from '../api'
import { slotEntries, buildIndex } from '../components/timetable/lessonLogic'

const timetableKey = (id) => ['timetable', id]

const at = (period) => ({ period_id: period.id, day_of_week: period.day_of_week, order: period.order })

let tempId = -1

/**
 * Editing the timetable by hand: place, move, take off, lock, undo.
 *
 * Every edit shows at once and the server is told afterwards, one request at a
 * time and in order, so two quick drops can't overtake each other. If the
 * server refuses one, only that edit is put back, and it says why. Its answer
 * replaces the guess, including the rules the timetable now breaks, which only
 * the server can work out.
 */
export function useTimetableEdits(timetableId, periodsById, { onRefused, onMoveRefused }) {
  const queryClient = useQueryClient()
  const key = timetableKey(timetableId)
  const queue = useRef(Promise.resolve())
  const stack = useRef([])
  const [undoCount, setUndoCount] = useState(0)
  // Bumped after each saved edit, so the rule forecast is asked for again.
  const [revision, setRevision] = useState(0)
  const handlers = useRef({ onRefused, onMoveRefused })
  handlers.current = { onRefused, onMoveRefused }

  useEffect(() => {
    stack.current = []
    setUndoCount(0)
  }, [timetableId])

  const change = useCallback(
    (fn) => queryClient.setQueryData(timetableKey(timetableId), (prev) => (prev ? { ...prev, entries: fn(prev.entries) } : prev)),
    [queryClient, timetableId],
  )

  const settle = useCallback((res, tempIds = []) => {
    queryClient.setQueryData(timetableKey(timetableId), (prev) => {
      if (!prev) return prev
      const gone = new Set([...(res.removed_ids ?? []), ...tempIds])
      const updated = new Map((res.entries ?? []).map((e) => [e.id, e]))
      const kept = []
      for (const e of prev.entries) {
        if (gone.has(e.id)) continue
        kept.push(updated.get(e.id) ?? e)
        updated.delete(e.id)
      }
      return { ...prev, entries: [...kept, ...updated.values()], violations: res.violations ?? prev.violations }
    })
    setRevision((r) => r + 1)
  }, [queryClient, timetableId])

  const send = useCallback((request, { tempIds, rollback, refused }) => {
    queue.current = queue.current.then(async () => {
      try {
        settle(await request(), tempIds)
      } catch (err) {
        rollback()
        ;(refused ?? handlers.current.onRefused)(err)
      }
    })
    return queue.current
  }, [settle])

  const remember = (undo) => {
    stack.current.push(undo)
    if (stack.current.length > 50) stack.current.shift()
    setUndoCount(stack.current.length)
  }

  const current = () => queryClient.getQueryData(key)?.entries ?? []

  const removeRaw = (sections, period, entriesGone, record) => {
    const ids = new Set(entriesGone.map((e) => e.id))
    change((list) => list.filter((e) => !ids.has(e.id)))
    if (record) {
      remember(() => restoreRaw(entriesGone))
    }
    return send(() => api.removeSlot(timetableId, sections[0], period.id), {
      rollback: () => change((list) => [...list, ...entriesGone]),
    })
  }

  const restoreRaw = (rows) => {
    const temps = rows.map((e) => ({ ...e, id: tempId-- }))
    change((list) => [...list, ...temps])
    const ids = new Set(temps.map((e) => e.id))
    return send(() => api.restoreSlot(timetableId, rows), {
      tempIds: temps.map((e) => e.id),
      rollback: () => change((list) => list.filter((e) => !ids.has(e.id))),
    })
  }

  const moveRaw = (sections, fromId, toId, record) => {
    const from = periodsById.get(fromId)
    const to = periodsById.get(toId)
    const inSections = new Set(sections)
    const moveCells = (a, b) => change((list) => list.map((e) => (inSections.has(e.class_group_id) && e.period_id === a.id ? { ...e, ...at(b) } : e)))
    moveCells(from, to)
    if (record) remember(() => moveRaw(sections, toId, fromId, false))
    return send(() => api.moveSlot(timetableId, sections[0], fromId, toId), {
      rollback: () => moveCells(to, from),
      refused: (err) => handlers.current.onMoveRefused(sections[0], fromId, toId, err),
    })
  }

  const place = (lesson, teacherId, period, teacherIds, names) => {
    const base = { ...at(period), locked: false, room_id: null, room_name: null, lab_batch: null, subject_frozen: false, assistant_teacher_id: null, assistant_teacher_name: null }
    let temps
    if (lesson.kind === 'subject') {
      temps = [{
        ...base, id: tempId--, class_group_id: lesson.class_group_id, subject_id: lesson.subject_id, subject_name: lesson.label,
        teacher_id: teacherId, teacher_name: names?.(teacherId), elective_block_id: null, elective_block_name: null, elective_option_id: null,
      }]
    } else {
      temps = []
      let mineUsed = false
      const list = current()
      for (const o of lesson.options) {
        const held = list.find((e) => e.elective_option_id === o.option_id && e.teacher_id != null)?.teacher_id
        let t = held ?? o.preferred_teacher_id ?? null
        if (t == null && !mineUsed && o.teacher_ids.includes(teacherId)) {
          t = teacherId
        }
        if (t === teacherId) mineUsed = true
        for (const sid of o.section_ids) {
          temps.push({
            ...base, id: tempId--, class_group_id: sid, subject_id: o.subject_id, subject_name: o.subject_name, teacher_id: t,
            teacher_name: t != null ? names?.(t) : null, elective_block_id: lesson.block_id, elective_block_name: lesson.label, elective_option_id: o.option_id,
          })
        }
      }
    }
    const ids = temps.map((e) => e.id)
    const idSet = new Set(ids)
    change((list) => [...list, ...temps])
    remember(() => {
      const rows = current().filter((e) => e.period_id === period.id && lesson.section_ids.includes(e.class_group_id))
      return removeRaw(lesson.section_ids, period, rows, false)
    })
    void teacherIds
    return send(
      () => api.placeLesson(timetableId, lesson.kind === 'subject'
        ? { class_group_id: lesson.class_group_id, subject_id: lesson.subject_id, teacher_id: teacherId, period_id: period.id }
        : { block_id: lesson.block_id, teacher_id: teacherId, period_id: period.id }),
      { tempIds: ids, rollback: () => change((list) => list.filter((e) => !idSet.has(e.id))) },
    )
  }

  const lockRaw = (sections, periodId, locked, record) => {
    const inSections = new Set(sections)
    const mark = (value) => change((list) => list.map((e) => (inSections.has(e.class_group_id) && e.period_id === periodId ? { ...e, locked: value } : e)))
    mark(locked)
    if (record) remember(() => lockRaw(sections, periodId, !locked, false))
    return send(() => api.lockSlot(timetableId, sections[0], periodId, locked), { rollback: () => mark(!locked) })
  }

  return {
    undoCount,
    revision,
    place,
    move: (slot, fromId, period) => moveRaw(slot.sections, fromId, period.id, true),
    remove: (slot, period) => removeRaw(slot.sections, period, slot.entries, true),
    lock: (slot, sectionId, periodId, locked) => lockRaw(slot.sections, periodId, locked, true),
    undo: () => {
      const last = stack.current.pop()
      setUndoCount(stack.current.length)
      return last?.()
    },
    slotAt: (sectionId, periodId) => slotEntries(buildIndex(current()), sectionId, periodId),
  }
}

/** The lessons the school's plan asks for: the cards. */
export function useLessons(schoolId) {
  return useQuery({
    queryKey: ['lessons', schoolId],
    queryFn: () => api.listLessons(schoolId),
    enabled: schoolId != null,
    // The plan changes on other steps, and this page should reflect it on arrival.
    staleTime: 0,
  })
}

/**
 * What this teacher's lessons would break in each period, asked for as soon as
 * the teacher is selected and again after each saved edit. Until the new answer
 * arrives the last one stands, so the amber doesn't flicker.
 */
export function useForecast(timetableId, teacherId, revision, enabled) {
  const { data } = useQuery({
    queryKey: ['forecast', timetableId, teacherId, revision],
    queryFn: () => api.forecast(timetableId, teacherId),
    enabled: enabled && timetableId != null && teacherId != null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    gcTime: 60_000,
    retry: false,
  })
  return useMemo(() => data ?? null, [data])
}

/** Start a new, empty version. */
export function useStartBlank(schoolId) {
  const queryClient = useQueryClient()
  return async () => {
    const created = await api.startBlankTimetable(schoolId)
    queryClient.setQueryData(timetableKey(created.id), created)
    const { entries: _entries, ...summary } = created
    queryClient.setQueryData(['timetables', schoolId], (prev = []) => [...prev.map((t) => ({ ...t, is_current: false })), summary])
    queryClient.invalidateQueries({ queryKey: ['timetables', schoolId] })
    return created
  }
}
