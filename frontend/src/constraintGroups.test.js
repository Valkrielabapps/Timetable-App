import { describe, expect, it } from 'vitest'
import { filterOptions, matches, NO_FILTERS, organise, placesFor, problemsWith } from './constraintGroups'

/**
 * Filing saved rules under who they are about.
 *
 * The property under test is that a rule is found where someone would look
 * for it - under the most specific thing it names - and that a rule needing
 * attention is never buried among the ones that are fine.
 */

let nextId = 1
const rule = (about = {}, extra = {}) => ({
  id: nextId++,
  description: 'A rule.',
  enforced: true,
  conflicts: [],
  is_hard: true,
  about: { teachers: [], subjects: [], class_groups: [], every: [], ...about },
  ...extra,
})

describe('where a rule is filed', () => {
  it('under the teacher it names', () => {
    expect(placesFor(rule({ teachers: ['Mrs. Rao'] }))).toEqual([{ category: 'teachers', group: 'Mrs. Rao' }])
  })

  it('under the teacher before the section or subject it also names', () => {
    // "Mrs. Rao never teaches 11A Physics in period 1" is a fact about her week.
    const r = rule({ teachers: ['Mrs. Rao'], class_groups: ['Grade 11 - A'], subjects: ['Physics'] })
    expect(placesFor(r)).toEqual([{ category: 'teachers', group: 'Mrs. Rao' }])
  })

  it('under the section before the subject', () => {
    const r = rule({ class_groups: ['Grade 11 - A'], subjects: ['PE'] })
    expect(placesFor(r)).toEqual([{ category: 'sections', group: 'Grade 11 - A' }])
  })

  it('under the subject when that is all it names', () => {
    expect(placesFor(rule({ subjects: ['PE'] }))).toEqual([{ category: 'subjects', group: 'PE' }])
  })

  it('under every teacher it names, so it is found under either', () => {
    expect(placesFor(rule({ teachers: ['Mr. Khan', 'Mrs. Rao'] }))).toEqual([
      { category: 'teachers', group: 'Mr. Khan' },
      { category: 'teachers', group: 'Mrs. Rao' },
    ])
  })

  it('under "Every teacher" for a rule about all of them', () => {
    // "No teacher teaches more than 6 periods a day."
    expect(placesFor(rule({ every: ['teacher'] }))).toEqual([{ category: 'teachers', group: 'Every teacher' }])
  })

  it('under a named subject before "every section"', () => {
    // "No section has more than 2 PE periods a day" - looked for under PE.
    expect(placesFor(rule({ subjects: ['PE'], every: ['class_group'] }))).toEqual([
      { category: 'subjects', group: 'PE' },
    ])
  })

  it('under the whole school when it names nothing and ranges over nobody', () => {
    expect(placesFor(rule())).toEqual([{ category: 'school', group: null }])
  })

  it('under the whole school when the server sent nothing about it', () => {
    // An older response; better filed somewhere than dropped.
    expect(placesFor({ id: 1 })).toEqual([{ category: 'school', group: null }])
  })
})

describe('what needs attention', () => {
  it('nothing, for a rule that is applied and unbroken', () => {
    expect(problemsWith(rule())).toEqual([])
  })

  it('a rule that is not applied', () => {
    expect(problemsWith(rule({}, { enforced: false }))).toEqual(['Not applied when generating'])
  })

  it('a rule that contradicts another', () => {
    expect(problemsWith(rule({}, { conflicts: ['x'] }))).toEqual(['Contradicts another rule'])
  })

  it('a rule the current timetable breaks', () => {
    const r = rule()
    expect(problemsWith(r, new Set([r.id]))).toEqual(['Broken by the current timetable'])
  })
})

describe('organising the list', () => {
  it('pulls rules needing attention out of their groups', () => {
    const broken = rule({ teachers: ['Mrs. Rao'] }, { enforced: false })
    const fine = rule({ teachers: ['Mrs. Rao'] })
    const { attention, categories } = organise([broken, fine])
    expect(attention.map((a) => a.constraint.id)).toEqual([broken.id])
    expect(categories[0].groups[0].items.map((c) => c.id)).toEqual([fine.id])
  })

  it('orders categories teachers, sections, subjects, whole school, leaving out empty ones', () => {
    const { categories } = organise([rule(), rule({ subjects: ['PE'] }), rule({ teachers: ['Mrs. Rao'] })])
    expect(categories.map((c) => c.key)).toEqual(['teachers', 'subjects', 'school'])
  })

  it('puts "Every teacher" first and the rest by name', () => {
    const { categories } = organise([
      rule({ teachers: ['Ms. Verma'] }),
      rule({ every: ['teacher'] }),
      rule({ teachers: ['Ananya Sen'] }),
    ])
    // Ananya would come before "Every" alphabetically.
    expect(categories[0].groups.map((g) => g.name)).toEqual(['Every teacher', 'Ananya Sen', 'Ms. Verma'])
  })

  it('counts a rule listed under two teachers once', () => {
    const { categories } = organise([rule({ teachers: ['Mr. Khan', 'Mrs. Rao'] })])
    expect(categories[0].count).toBe(1)
    expect(categories[0].groups).toHaveLength(2)
  })

  it('keeps the order rules were added within a group', () => {
    const a = rule({ subjects: ['PE'] })
    const b = rule({ subjects: ['PE'] })
    const { categories } = organise([b, a])
    expect(categories[0].groups[0].items.map((c) => c.id)).toEqual([a.id, b.id])
  })
})

describe('searching and filtering', () => {
  const rao = rule({ teachers: ['Mrs. Rao'], subjects: ['Physics'] }, { description: 'Mrs. Rao is free on Fridays.' })
  const pe = rule({ subjects: ['PE'] }, { description: 'No PE in period 1.', source_text: 'pe never first thing', is_hard: false })

  it('searches the sentence', () => {
    expect(matches(rao, { ...NO_FILTERS, text: 'fridays' })).toBe(true)
    expect(matches(pe, { ...NO_FILTERS, text: 'fridays' })).toBe(false)
  })

  it('searches what was typed and the names it is about', () => {
    expect(matches(pe, { ...NO_FILTERS, text: 'first thing' })).toBe(true)
    expect(matches(rao, { ...NO_FILTERS, text: 'physics' })).toBe(true)
  })

  it('filters by teacher, subject and section', () => {
    expect(matches(rao, { ...NO_FILTERS, teacher: 'Mrs. Rao' })).toBe(true)
    expect(matches(pe, { ...NO_FILTERS, teacher: 'Mrs. Rao' })).toBe(false)
    expect(matches(pe, { ...NO_FILTERS, subject: 'PE' })).toBe(true)
    expect(matches(pe, { ...NO_FILTERS, section: 'Grade 11 - A' })).toBe(false)
  })

  it('filters rules from preferences', () => {
    expect(matches(pe, { ...NO_FILTERS, strength: 'preferences' })).toBe(true)
    expect(matches(pe, { ...NO_FILTERS, strength: 'rules' })).toBe(false)
    expect(matches(rao, { ...NO_FILTERS, strength: 'rules' })).toBe(true)
  })

  it('filters the attention list too', () => {
    const broken = rule({ subjects: ['PE'] }, { enforced: false })
    expect(organise([broken], { filters: { ...NO_FILTERS, teacher: 'Mrs. Rao' } }).attention).toEqual([])
  })

  it('offers only names some rule mentions', () => {
    expect(filterOptions([rao, pe])).toEqual({
      teachers: ['Mrs. Rao'], subjects: ['PE', 'Physics'], sections: [],
    })
  })
})
