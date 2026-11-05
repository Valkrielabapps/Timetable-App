/**
 * What can go where, worked out in the browser from the timetable it already
 * holds, so picking a lesson up colours the grid at once. The server still
 * checks every drop. It also sends what can't be known here, which rules a
 * lesson would break (see forecast in backend/app/services/lesson_placing.py),
 * ahead of time when a teacher is selected.
 */

const kindOf = (p) => p?.kind ?? (p?.is_break ? 'break' : 'lesson')

/** "9-A": short enough for a lesson card or a grid cell. */
export function sectionShort(cg) {
  if (!cg) return ''
  if (!cg.grade) return cg.name
  const number = cg.grade.match(/\d+/)
  return `${number ? number[0] : cg.grade}-${cg.name}`
}

/** "Grade 9-A": a timetable's heading. */
export const sectionTitle = (cg) => (cg?.grade ? `${cg.grade}-${cg.name}` : cg?.name ?? '')

/** Everything looked up during a drag, in one pass over the entries. */
export function buildIndex(entries) {
  const byPeriod = new Map()
  const atSection = new Map()
  for (const e of entries) {
    if (!byPeriod.has(e.period_id)) byPeriod.set(e.period_id, [])
    byPeriod.get(e.period_id).push(e)
    const key = `${e.class_group_id}:${e.period_id}`
    if (!atSection.has(key)) atSection.set(key, [])
    atSection.get(key).push(e)
  }
  return { byPeriod, atSection, at: (sectionId, periodId) => atSection.get(`${sectionId}:${periodId}`) ?? [] }
}

/** Why a section can't have a lesson in this period, or null. */
export function noLessonReason(period, section) {
  if (!period) return 'Nothing can be scheduled there'
  const kind = kindOf(period)
  if (kind === 'break') return 'Nothing can be scheduled in a break'
  if (kind === 'class_teacher') return 'Nothing can be scheduled in the class teacher period'
  if (kind === 'zero') return 'Nothing can be scheduled in the zero period'
  const grade = section?.grade
  if (period.zero_all || (grade != null && (period.zero_grades ?? []).includes(grade))) {
    return `That's ${grade ?? 'this section'}'s zero period`
  }
  if (grade != null && (period.off_grades ?? []).includes(grade)) return `${grade}'s school day is over by then`
  return null
}

const lessonName = (e) => e.elective_block_name ?? e.subject_name

function busyReason(ctx, sectionIds, teacherIds, periodId, skip) {
  for (const sid of sectionIds) {
    const there = ctx.index.at(sid, periodId).filter((e) => !skip.has(e.id))
    if (there.length > 0) {
      const e = there[0]
      const who = there.length > 1 ? 'several teachers' : e.teacher_name
      return `${sectionShort(ctx.sections.get(sid))} already has ${lessonName(e)}${who ? ` with ${who}` : ''} here`
    }
  }
  const here = (ctx.index.byPeriod.get(periodId) ?? []).filter((e) => !skip.has(e.id))
  for (const t of teacherIds) {
    const e = here.find((x) => x.teacher_id === t)
    if (e) return `${ctx.teachers.get(t)?.name ?? 'The teacher'} already teaches ${lessonName(e)} ${sectionShort(ctx.sections.get(e.class_group_id))} here`
  }
  return null
}

function warnFrom(ctx, teacherIds, periodId, serverSays) {
  const reasons = []
  if (serverSays?.status === 'warn' && serverSays.reason) {
    reasons.push(...serverSays.reason.split('; ').map((r) => r.replace(/^Breaks “(.*)”$/, '$1')))
  }
  for (const t of teacherIds) {
    const teacher = ctx.teachers.get(t)
    const line = `${teacher?.name} is marked unavailable then`
    if (teacher?.unavailable_period_ids?.includes(periodId) && !reasons.includes(line)) reasons.push(line)
  }
  return reasons
}

const verdict = (reasons) =>
  reasons.length
    ? { kind: 'warn', text: `You can drop here, but it breaks: ${reasons.join('; ')}`, breaks: reasons }
    : { kind: 'ok', text: 'Free slot, no rules broken' }

/** Teachers a lesson would occupy if this teacher places it. */
export function teachersOfLesson(lesson, teacherId, entries) {
  if (lesson.kind === 'subject') return [teacherId]
  const out = new Set([teacherId])
  for (const o of lesson.options) {
    const held = entries.find((e) => e.elective_option_id === o.option_id && e.teacher_id != null)?.teacher_id
    const fixed = held ?? o.preferred_teacher_id
    if (fixed != null) out.add(fixed)
  }
  return [...out]
}

/** Dropping a lesson card here: { kind: ok|warn|bad, text, breaks? }. */
export function judgeCard(lesson, teacherIds, period, ctx) {
  if (lesson.frozen) return { kind: 'bad', text: `${lesson.frozen} is frozen` }
  for (const sid of lesson.section_ids) {
    const section = ctx.sections.get(sid)
    if (ctx.frozen.has(sid)) return { kind: 'bad', text: `${sectionShort(section)} is frozen` }
    const none = noLessonReason(period, section)
    if (none) return { kind: 'bad', text: none }
  }
  const busy = busyReason(ctx, lesson.section_ids, teacherIds, period.id, new Set())
  if (busy) return { kind: 'bad', text: busy }
  return verdict(warnFrom(ctx, teacherIds, period.id, ctx.forecast?.cards?.[lesson.key]?.[period.id]))
}

/** Everything that moves with a slot: a shared block's other sections too. */
export function slotEntries(index, sectionId, periodId) {
  const sections = [sectionId]
  for (let i = 0; i < sections.length; i++) {
    const blocks = new Set(index.at(sections[i], periodId).map((e) => e.elective_block_id).filter((b) => b != null))
    if (blocks.size === 0) continue
    for (const o of index.byPeriod.get(periodId) ?? []) {
      if (blocks.has(o.elective_block_id) && !sections.includes(o.class_group_id)) sections.push(o.class_group_id)
    }
  }
  return { sections, entries: sections.flatMap((sid) => index.at(sid, periodId)) }
}

/** Why a slot can't be picked up at all, or null. */
export function cantMoveReason(slot, ctx) {
  for (const sid of slot.sections) {
    if (ctx.frozen.has(sid)) return `${sectionShort(ctx.sections.get(sid))} is frozen`
  }
  const frozen = slot.entries.find((e) => e.subject_frozen)
  if (frozen) return `${frozen.subject_name} is frozen`
  if (slot.entries.some((e) => e.locked)) return 'This lesson is locked. Click it to unlock it first'
  return null
}

/** Moving a slot here: { kind: origin|ok|warn|bad, text, breaks? }. */
export function judgeSlot(slot, fromPeriodId, period, ctx) {
  if (period.id === fromPeriodId) return { kind: 'origin', text: 'Where this lesson is now' }
  for (const sid of slot.sections) {
    const none = noLessonReason(period, ctx.sections.get(sid))
    if (none) return { kind: 'bad', text: none }
  }
  const skip = new Set(slot.entries.map((e) => e.id))
  const teacherIds = [...new Set(slot.entries.map((e) => e.teacher_id).filter((t) => t != null))]
  const busy = busyReason(ctx, slot.sections, teacherIds, period.id, skip)
  if (busy) return { kind: 'bad', text: busy }
  const here = (ctx.index.byPeriod.get(period.id) ?? []).filter((e) => !skip.has(e.id))
  for (const e of slot.entries) {
    const room = e.room_id != null && here.find((o) => o.room_id === e.room_id)
    if (room) return { kind: 'bad', text: `${e.room_name ?? 'The room'} is in use by ${sectionShort(ctx.sections.get(room.class_group_id))} here` }
  }
  const server = ctx.forecast?.slots?.[`${slot.sections[0]}:${fromPeriodId}`]?.[period.id]
  if (server?.status === 'blocked') return { kind: 'bad', text: server.reason }
  return verdict(warnFrom(ctx, teacherIds, period.id, server))
}

/** A lesson card as a teacher sees it. */
export function cardState(lesson, teacherId, entries, frozenSections) {
  const mine = lesson.kind === 'subject'
    ? entries.filter((e) => e.class_group_id === lesson.class_group_id && e.subject_id === lesson.subject_id && e.elective_block_id == null)
    : entries.filter((e) => e.elective_block_id === lesson.block_id)
  const placed = new Set(mine.map((e) => e.period_id)).size
  const left = lesson.periods_per_week - placed
  let takenBy = null
  if (lesson.kind === 'subject') {
    const holder = mine.find((e) => e.teacher_id != null)?.teacher_id
    if (holder != null && holder !== teacherId) takenBy = holder
  } else {
    const possible = lesson.options.filter((o) => o.teacher_ids.includes(teacherId))
    const holders = possible.map((o) => mine.find((e) => e.elective_option_id === o.option_id && e.teacher_id != null)?.teacher_id)
    if (holders.length > 0 && holders.every((h) => h != null && h !== teacherId)) takenBy = holders[0]
  }
  const frozen = lesson.frozen ?? (lesson.section_ids.some((s) => frozenSections.has(s)) ? 'This section' : null)
  return { placed, left, takenBy, frozen, off: left <= 0 || takenBy != null || !!frozen || lesson.split }
}

/** The lessons a teacher can take, lowest section first. */
export function lessonsForTeacher(lessons, teacherId, sectionOrder) {
  const rank = (l) => Math.min(...l.section_ids.map((s) => sectionOrder.get(s) ?? 9999))
  return lessons
    .filter((l) => l.teacher_ids.includes(teacherId))
    .sort((a, b) => rank(a) - rank(b) || a.label.localeCompare(b.label))
}

/** "Physics, Grades 9-12 · Science, Grades 7-8": what a teacher is set up for. */
export function qualificationText(teacher, subjects) {
  const names = (teacher.qualified_subject_ids ?? []).map((id) => subjects.find((s) => s.id === id)?.name).filter(Boolean)
  if (names.length === 0) return 'No subjects set up yet'
  const grades = teacher.qualified_grades ?? []
  const numbers = grades.map((g) => Number(g.match(/\d+/)?.[0])).sort((a, b) => a - b)
  let where = 'all grades'
  if (grades.length === 1) where = grades[0]
  else if (grades.length > 1) {
    const unbroken = numbers.every((n, i) => !Number.isNaN(n) && (i === 0 || n === numbers[i - 1] + 1))
    where = unbroken ? `Grades ${numbers[0]}-${numbers[numbers.length - 1]}` : grades.join(', ')
  }
  return `${names.join(', ')}, ${where}`
}

/** What a period row looks like: a numbered lesson row or a thin band. */
export function buildRows(periods) {
  const days = [...new Set(periods.map((p) => p.day_of_week))].sort((a, b) => a - b)
  const orders = [...new Set(periods.map((p) => p.order))].sort((a, b) => a - b)
  const byKey = new Map(periods.map((p) => [`${p.day_of_week}:${p.order}`, p]))
  const rows = orders.map((order) => {
    const here = periods.filter((p) => p.order === order)
    const lesson = here.find((p) => kindOf(p) === 'lesson')
    if (lesson) return { order, band: false, label: lesson.number ?? order + 1 }
    const kind = kindOf(here[0])
    const label = kind === 'class_teacher' ? 'Class teacher' : kind === 'zero' ? 'Zero period' : here.find((p) => p.label)?.label || 'Break'
    return { order, band: true, kind, label }
  })
  return { days, rows, at: (day, order) => byKey.get(`${day}:${order}`) ?? null }
}
