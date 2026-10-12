import { describe, expect, it } from 'vitest'
import { DEFAULT_STRUCTURE, fromServer, layoutDay, lessonsOn, zeroIsNumbered } from './timetableStructure'

/**
 * Laying out a day from the school's structure, for the preview.
 *
 * It mirrors the server's layout() so the preview shows exactly the periods
 * saving will make - the cases here are the same ones the backend tests pin
 * down (backend/tests/test_timetable_structure.py).
 */

const s = (patch = {}) => ({ ...DEFAULT_STRUCTURE, ...patch })
const shape = (slots) =>
  slots.map((x) =>
    x.kind === 'lesson' ? (x.zeroFor?.length ? `${x.number}*` : String(x.number)) : x.kind === 'break' ? x.label : x.kind,
  )

describe('a day', () => {
  it('has the same numbered periods every day', () => {
    expect(shape(layoutDay(s(), 0))).toEqual(['1', '2', '3', '4', '5', '6', '7', '8'])
  })

  it('puts breaks between numbers', () => {
    const day = layoutDay(s({ breaks: [{ after: 3, label: 'Recess' }, { after: 6, label: 'Lunch' }] }), 0)
    expect(shape(day)).toEqual(['1', '2', '3', 'Recess', '4', '5', '6', 'Lunch', '7', '8'])
  })

  it('puts the class teacher period before period 1 without renumbering it', () => {
    const day = layoutDay(s({ class_teacher_period: { enabled: true, after: 0 } }), 0)
    expect(shape(day).slice(0, 2)).toEqual(['class_teacher', '1'])
  })

  it('can put the class teacher period later', () => {
    const day = layoutDay(s({ class_teacher_period: { enabled: true, after: 2 } }), 0)
    expect(shape(day).slice(0, 4)).toEqual(['1', '2', 'class_teacher', '3'])
  })

  it('gives a shorter day fewer periods and only the breaks that fit', () => {
    const structure = s({ days: [0, 5], short_days: { 5: 4 }, breaks: [{ after: 3, label: 'B' }, { after: 6, label: 'L' }] })
    expect(shape(layoutDay(structure, 5))).toEqual(['1', '2', '3', 'B', '4'])
  })
})

describe('a shorter day', () => {
  it('does not end on a break or class teacher period meant for after period 4 of a full day', () => {
    const structure = s({
      days: [0, 5], short_days: { 5: 4 }, breaks: [{ after: 4, label: 'Lunch' }],
      class_teacher_period: { enabled: true, after: 4 },
    })
    expect(shape(layoutDay(structure, 5))).toEqual(['1', '2', '3', '4'])
    expect(shape(layoutDay(structure, 0))).toContain('Lunch')
  })
})

describe('the zero period', () => {
  const whole = (placement) => ({ enabled: true, scope: 'school', placements: [{ grade: null, ...placement }] })

  it('is its own unnumbered slot when it is the same for everyone every day', () => {
    const structure = s({ zero_period: whole({ every_day: 5 }) })
    expect(zeroIsNumbered(structure)).toBe(false)
    expect(shape(layoutDay(structure, 0))).toEqual(['1', '2', '3', '4', 'zero', '5', '6', '7', '8'])
  })

  it('can come last', () => {
    expect(shape(layoutDay(s({ zero_period: whole({ every_day: 9 }) }), 0)).at(-1)).toBe('zero')
  })

  it('is a numbered period kept free when it moves between days', () => {
    const structure = s({ days: [0, 1], zero_period: whole({ by_day: { 0: 2, 1: 7 } }) })
    expect(zeroIsNumbered(structure)).toBe(true)
    expect(lessonsOn(structure, 0)).toBe(9)
    expect(shape(layoutDay(structure, 0))).toEqual(['1', '2*', '3', '4', '5', '6', '7', '8', '9'])
    expect(shape(layoutDay(structure, 1))).toEqual(['1', '2', '3', '4', '5', '6', '7*', '8', '9'])
  })

  it('is a numbered period kept free per grade, naming who it is for', () => {
    const structure = s({
      zero_period: {
        enabled: true,
        scope: 'grade',
        placements: [{ grade: 'Grade 6', every_day: 1 }, { grade: 'Grade 7', every_day: 1 }],
      },
    })
    expect(layoutDay(structure, 0)[0].zeroFor).toEqual(['Grade 6', 'Grade 7'])
  })

  it('is nothing when switched off', () => {
    const structure = s({ zero_period: { ...whole({ every_day: 3 }), enabled: false } })
    expect(shape(layoutDay(structure, 0))).toEqual(['1', '2', '3', '4', '5', '6', '7', '8'])
  })
})

describe('reading a structure from the server', () => {
  it('turns object keys back into day numbers', () => {
    const read = fromServer({
      ...DEFAULT_STRUCTURE,
      short_days: { 5: 4 },
      zero_period: { enabled: true, scope: 'school', placements: [{ grade: null, every_day: null, by_day: { 0: 2 } }] },
    })
    expect(read.short_days).toEqual({ 5: 4 })
    expect(Object.keys(read.zero_period.placements[0].by_day)).toEqual(['0'])
    expect(read.zero_period.placements[0].by_day[0]).toBe(2)
  })

  it('starts from Mon-Fri, eight periods, when the school has none', () => {
    expect(fromServer(null)).toEqual(DEFAULT_STRUCTURE)
  })
})
