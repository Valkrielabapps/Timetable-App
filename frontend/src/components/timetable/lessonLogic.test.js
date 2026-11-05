import { describe, expect, it } from 'vitest'
import {
  buildIndex, buildRows, cantMoveReason, cardState, judgeCard, judgeSlot, lessonsForTeacher, noLessonReason,
  qualificationText, sectionShort, sectionTitle, slotEntries, teachersOfLesson,
} from './lessonLogic'

/**
 * What can go where, decided in the browser so the colours are there the moment
 * a lesson is picked up. These have to agree with what the server then accepts.
 */

const A = { id: 1, grade: 'Grade 9', name: 'A' }
const B = { id: 2, grade: 'Grade 9', name: 'B' }
const P1 = { id: 11, day_of_week: 0, order: 0, number: 1, kind: 'lesson' }
const P2 = { id: 12, day_of_week: 0, order: 1, number: 2, kind: 'lesson' }
const entry = (id, section, period, teacher, more = {}) => ({
  id, class_group_id: section, period_id: period, teacher_id: teacher, subject_id: 5, subject_name: 'Maths',
  teacher_name: `T${teacher}`, room_id: null, locked: false, subject_frozen: false, elective_block_id: null, ...more,
})
const lesson = { key: 'r1', kind: 'subject', class_group_id: 1, section_ids: [1], subject_id: 9, label: 'Physics', periods_per_week: 3, teacher_ids: [7], options: [], split: false, frozen: null }

const ctx = (entries, more = {}) => ({
  index: buildIndex(entries),
  sections: new Map([[1, A], [2, B]]),
  teachers: new Map([[7, { id: 7, name: 'Mrs Susan' }], [8, { id: 8, name: 'Mr George' }]]),
  frozen: new Set(),
  forecast: null,
  ...more,
})

describe('dropping a lesson card', () => {
  it('is green on a free slot', () => {
    expect(judgeCard(lesson, [7], P1, ctx([])).kind).toBe('ok')
  })

  it('is red when the section already has a lesson', () => {
    const v = judgeCard(lesson, [7], P1, ctx([entry(1, 1, 11, 8)]))
    expect(v.kind).toBe('bad')
    expect(v.text).toBe('9-A already has Maths with T8 here')
  })

  it('is red when the teacher is teaching elsewhere', () => {
    const v = judgeCard(lesson, [7], P1, ctx([entry(1, 2, 11, 7)]))
    expect(v.kind).toBe('bad')
    expect(v.text).toBe('Mrs Susan already teaches Maths 9-B here')
  })

  it('is amber when the server says a rule would break, and can still be dropped', () => {
    const forecast = { cards: { r1: { 11: { status: 'warn', reason: 'Mrs Susan: no classes after break' } } } }
    const v = judgeCard(lesson, [7], P1, ctx([], { forecast }))
    expect(v.kind).toBe('warn')
    expect(v.breaks).toEqual(['Mrs Susan: no classes after break'])
    expect(v.text).toContain('You can drop here, but it breaks')
  })

  it('is amber when the teacher is marked unavailable', () => {
    const teachers = new Map([[7, { id: 7, name: 'Mrs Susan', unavailable_period_ids: [11] }]])
    expect(judgeCard(lesson, [7], P1, ctx([], { teachers })).kind).toBe('warn')
  })

  it('takes a clash over a rule: red beats amber', () => {
    const forecast = { cards: { r1: { 11: { status: 'warn', reason: 'x' } } } }
    expect(judgeCard(lesson, [7], P1, ctx([entry(1, 1, 11, 8)], { forecast })).kind).toBe('bad')
  })

  it('is red in a frozen section, a frozen subject and a break', () => {
    expect(judgeCard(lesson, [7], P1, ctx([], { frozen: new Set([1]) })).text).toBe('9-A is frozen')
    expect(judgeCard({ ...lesson, frozen: 'Physics' }, [7], P1, ctx([])).text).toBe('Physics is frozen')
    expect(judgeCard(lesson, [7], { ...P1, kind: 'break' }, ctx([])).kind).toBe('bad')
  })

  it('checks every section and teacher of a block', () => {
    const block = { ...lesson, kind: 'block', section_ids: [1, 2] }
    expect(judgeCard(block, [7, 8], P1, ctx([entry(1, 2, 11, 3)])).text).toContain('9-B already has')
    expect(judgeCard(block, [7, 8], P1, ctx([entry(1, 3, 11, 8)])).text).toContain('Mr George already teaches')
  })
})

describe('moving a lesson that is already placed', () => {
  const slotOf = (entries, section, period) => slotEntries(buildIndex(entries), section, period)

  it('marks where it is now', () => {
    const list = [entry(1, 1, 11, 7)]
    expect(judgeSlot(slotOf(list, 1, 11), 11, P1, ctx(list)).kind).toBe('origin')
  })

  it('is green on a free slot, not counting itself', () => {
    const list = [entry(1, 1, 11, 7)]
    expect(judgeSlot(slotOf(list, 1, 11), 11, P2, ctx(list)).kind).toBe('ok')
  })

  it('refuses a slot with another lesson in it, rather than swapping', () => {
    const list = [entry(1, 1, 11, 7), entry(2, 1, 12, 8)]
    expect(judgeSlot(slotOf(list, 1, 11), 11, P2, ctx(list)).kind).toBe('bad')
  })

  it('refuses a room in use', () => {
    const list = [entry(1, 1, 11, 7, { room_id: 3, room_name: 'Lab 1' }), entry(2, 2, 12, 8, { room_id: 3 })]
    expect(judgeSlot(slotOf(list, 1, 11), 11, P2, ctx(list)).text).toBe('Lab 1 is in use by 9-B here')
  })

  it("takes the server's word on what it alone can know", () => {
    const list = [entry(1, 1, 11, 7)]
    const warn = { slots: { '1:11': { 12: { status: 'warn', reason: 'Breaks “No maths late”' } } } }
    expect(judgeSlot(slotOf(list, 1, 11), 11, P2, ctx(list, { forecast: warn })).breaks).toEqual(['No maths late'])
    const bad = { slots: { '1:11': { 12: { status: 'blocked', reason: 'Nope' } } } }
    expect(judgeSlot(slotOf(list, 1, 11), 11, P2, ctx(list, { forecast: bad })).text).toBe('Nope')
  })

  it('moves a shared block for every section in it', () => {
    const list = [
      entry(1, 1, 11, 7, { elective_block_id: 4 }), entry(2, 2, 11, 7, { elective_block_id: 4 }), entry(3, 2, 12, 8),
    ]
    const slot = slotOf(list, 1, 11)
    expect(slot.sections).toEqual([1, 2])
    expect(slot.entries).toHaveLength(2)
    expect(judgeSlot(slot, 11, P2, ctx(list)).text).toContain('9-B already has')
  })

  it("won't pick up a frozen or locked lesson", () => {
    const frozenSection = [entry(1, 1, 11, 7)]
    expect(cantMoveReason(slotOf(frozenSection, 1, 11), ctx(frozenSection, { frozen: new Set([1]) }))).toBe('9-A is frozen')
    const subject = [entry(1, 1, 11, 7, { subject_frozen: true })]
    expect(cantMoveReason(slotOf(subject, 1, 11), ctx(subject))).toBe('Maths is frozen')
    const locked = [entry(1, 1, 11, 7, { locked: true })]
    expect(cantMoveReason(slotOf(locked, 1, 11), ctx(locked))).toContain('locked')
    expect(cantMoveReason(slotOf(frozenSection, 1, 11), ctx(frozenSection))).toBeNull()
  })
})

describe('slots with no lessons', () => {
  it.each([
    [{ kind: 'break' }, A, 'a break'],
    [{ kind: 'class_teacher' }, A, 'class teacher'],
    [{ kind: 'zero' }, A, 'zero period'],
    [{ kind: 'lesson', zero_grades: ['Grade 9'] }, A, "Grade 9's zero period"],
    [{ kind: 'lesson', zero_all: true }, A, 'zero period'],
    [{ kind: 'lesson', off_grades: ['Grade 9'] }, A, 'day is over'],
  ])('%j refuses', (period, section, text) => {
    expect(noLessonReason(period, section)).toContain(text)
  })

  it("doesn't apply to another grade", () => {
    expect(noLessonReason({ kind: 'lesson', zero_grades: ['Grade 8'], off_grades: ['Grade 8'] }, A)).toBeNull()
  })
})

describe('a lesson card', () => {
  it('counts what is left', () => {
    const s = cardState({ ...lesson, subject_id: 5 }, 7, [entry(1, 1, 11, 7), entry(2, 1, 12, 7)], new Set())
    expect(s).toMatchObject({ placed: 2, left: 1, takenBy: null, off: false })
  })

  it('is finished when all are placed', () => {
    const s = cardState({ ...lesson, subject_id: 5, periods_per_week: 1 }, 7, [entry(1, 1, 11, 7)], new Set())
    expect(s).toMatchObject({ left: 0, off: true })
  })

  it('says when another teacher already has it', () => {
    const s = cardState({ ...lesson, subject_id: 5 }, 7, [entry(1, 1, 11, 8)], new Set())
    expect(s).toMatchObject({ takenBy: 8, off: true })
  })

  it("can't be dragged when frozen, or a split lab", () => {
    expect(cardState(lesson, 7, [], new Set([1])).off).toBe(true)
    expect(cardState({ ...lesson, frozen: 'Physics' }, 7, [], new Set()).off).toBe(true)
    expect(cardState({ ...lesson, split: true }, 7, [], new Set()).off).toBe(true)
  })

  it('counts a block by its periods, not its options', () => {
    const block = {
      ...lesson, kind: 'block', block_id: 4, subject_id: null,
      options: [{ option_id: 1, teacher_ids: [7] }, { option_id: 2, teacher_ids: [8] }],
    }
    const list = [
      entry(1, 1, 11, 7, { elective_block_id: 4, elective_option_id: 1 }),
      entry(2, 1, 11, 8, { elective_block_id: 4, elective_option_id: 2 }),
    ]
    expect(cardState(block, 7, list, new Set())).toMatchObject({ placed: 1, left: 2, takenBy: null })
    expect(cardState(block, 9, list, new Set()).takenBy).toBeNull()
  })

  it('sees a block as taken once someone else holds this teacher’s group', () => {
    const block = { ...lesson, kind: 'block', block_id: 4, options: [{ option_id: 1, teacher_ids: [7, 8] }] }
    const list = [entry(1, 1, 11, 8, { elective_block_id: 4, elective_option_id: 1 })]
    expect(cardState(block, 7, list, new Set()).takenBy).toBe(8)
  })

  it('knows who a block would occupy', () => {
    const block = { kind: 'block', options: [{ option_id: 1, preferred_teacher_id: 8 }, { option_id: 2, preferred_teacher_id: null }] }
    expect(teachersOfLesson(block, 7, []).sort()).toEqual([7, 8])
    expect(teachersOfLesson(lesson, 7, [])).toEqual([7])
  })

  it('lists lessons lowest section first', () => {
    const order = new Map([[1, 1], [2, 0]])
    const later = { ...lesson, key: 'a', section_ids: [1], label: 'A' }
    const earlier = { ...lesson, key: 'b', section_ids: [2], label: 'Z' }
    const notMine = { ...lesson, key: 'c', section_ids: [2], teacher_ids: [8] }
    expect(lessonsForTeacher([later, earlier, notMine], 7, order).map((l) => l.key)).toEqual(['b', 'a'])
  })
})

describe('names', () => {
  it('shortens sections', () => {
    expect(sectionShort(A)).toBe('9-A')
    expect(sectionShort({ grade: 'LKG', name: 'B' })).toBe('LKG-B')
    expect(sectionShort({ grade: null, name: 'Physics Hons' })).toBe('Physics Hons')
    expect(sectionTitle(A)).toBe('Grade 9-A')
  })

  it('says what a teacher is set up for', () => {
    const subjects = [{ id: 1, name: 'Physics' }]
    expect(qualificationText({ qualified_subject_ids: [1], qualified_grades: ['Grade 9', 'Grade 10', 'Grade 11'] }, subjects)).toBe('Physics, Grades 9-11')
    expect(qualificationText({ qualified_subject_ids: [1], qualified_grades: ['Grade 9', 'Grade 11'] }, subjects)).toBe('Physics, Grade 9, Grade 11')
    expect(qualificationText({ qualified_subject_ids: [1], qualified_grades: [] }, subjects)).toBe('Physics, all grades')
    expect(qualificationText({ qualified_subject_ids: [1], qualified_grades: ['Grade 9'] }, subjects)).toBe('Physics, Grade 9')
    expect(qualificationText({ qualified_subject_ids: [] }, subjects)).toBe('No subjects set up yet')
  })
})

describe('the rows of a week', () => {
  it('numbers lessons and turns a whole-school break into a band', () => {
    const { days, rows, at } = buildRows([
      { ...P1, number: 1 },
      { id: 13, day_of_week: 0, order: 1, kind: 'break', label: 'Recess' },
      { id: 14, day_of_week: 1, order: 1, kind: 'break', label: 'Recess' },
      { id: 15, day_of_week: 1, order: 0, kind: 'lesson', number: 1 },
      { id: 16, day_of_week: 0, order: 2, kind: 'class_teacher' },
    ])
    expect(days).toEqual([0, 1])
    expect(rows.map((r) => [r.band, r.label])).toEqual([[false, 1], [true, 'Recess'], [true, 'Class teacher']])
    expect(at(1, 0).id).toBe(15)
    expect(at(1, 2)).toBeNull()
  })
})
