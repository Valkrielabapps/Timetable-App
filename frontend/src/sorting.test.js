import { describe, expect, it } from 'vitest'
import { compareNames, matchesSearch, rankMatches, sortByName, sortSections, withoutTitle } from './sorting'

/**
 * Names sort by the name, never the title. Imported staff lists carry titles
 * however the school typed them, and "all the Mrs. together, then all the
 * Ms." is never the order anyone wants.
 */

describe('titles', () => {
  it.each([
    ['Mrs. Rao', 'Rao'],
    ['Mr Khan', 'Khan'],
    ['ms. shallu', 'shallu'],
    ['MISS Gupta', 'Gupta'],
    ['Mx. Lee', 'Lee'],
    ['Dr. Bose', 'Bose'],
    ['Dr Bose', 'Bose'],
    ['Prof. Iyer', 'Iyer'],
    ['Professor Iyer', 'Iyer'],
    ['Prof. Dr. Iyer', 'Iyer'],
    ['  Mrs.   Kamini Chandra ', 'Kamini Chandra'],
  ])('%s sorts as %s', (name, bare) => {
    expect(withoutTitle(name)).toBe(bare)
  })

  it.each(['Drishti', 'Mrinal', 'Msitu', 'Profulla', 'Missy'])('leaves %s alone - not a title', (name) => {
    expect(withoutTitle(name)).toBe(name)
  })

  it('keeps a name that is only a title', () => {
    expect(withoutTitle('Dr.')).toBe('Dr.')
  })
})

describe('alphabetical order', () => {
  it('orders a staff list by first name, whatever the titles', () => {
    const staff = ['Ms. Shallu', 'Mrs. Zareena', 'Mrs. Anjali', 'Dr. Bose', 'anil', 'Mr. Kamal']
    expect(staff.slice().sort(compareNames)).toEqual(
      ['anil', 'Mrs. Anjali', 'Dr. Bose', 'Mr. Kamal', 'Ms. Shallu', 'Mrs. Zareena'],
    )
  })

  it('ignores capitals', () => {
    expect(['maths', 'English', 'art'].sort(compareNames)).toEqual(['art', 'English', 'maths'])
  })

  it('counts numbers as numbers', () => {
    expect(['Grade 10', 'Grade 2', 'Grade 1'].sort(compareNames)).toEqual(['Grade 1', 'Grade 2', 'Grade 10'])
  })

  it('sorts objects by name without touching the original', () => {
    const list = [{ name: 'Mrs. Rao' }, { name: 'Anil' }]
    expect(sortByName(list).map((t) => t.name)).toEqual(['Anil', 'Mrs. Rao'])
    expect(list[0].name).toBe('Mrs. Rao')
  })

  it('sorts sections by grade, then section', () => {
    const sections = [
      { grade: 'Grade 10', name: 'A' }, { grade: 'Grade 2', name: 'B' }, { grade: 'Grade 2', name: 'A' },
    ]
    expect(sortSections(sections).map((s) => `${s.grade} ${s.name}`)).toEqual(
      ['Grade 2 A', 'Grade 2 B', 'Grade 10 A'],
    )
  })
})

describe('searching', () => {
  const staff = [{ name: 'Mrs. Rao' }, { name: 'Vinita' }, { name: 'Mr. Vikram' }, { name: 'Raghav' }, { name: 'Pravin' }]

  it('puts names starting with what was typed first, titles ignored', () => {
    expect(rankMatches(staff, 'vi').map((t) => t.name)).toEqual(['Mr. Vikram', 'Vinita', 'Pravin'])
  })

  it('ranks a name starting with what was typed above a surname that does', () => {
    // Alphabetically Anita comes first; as a match, Chirag is the better one.
    const people = [{ name: 'Anita Chawla' }, { name: 'Chirag' }]
    expect(rankMatches(people, 'ch').map((t) => t.name)).toEqual(['Chirag', 'Anita Chawla'])
  })

  it('finds a surname by its own word', () => {
    expect(rankMatches(staff, 'rao').map((t) => t.name)).toEqual(['Mrs. Rao'])
  })

  it('narrows by every word typed', () => {
    expect(matchesSearch('Mrs. Kamini Chandra Hindi Grade 4', 'kamini hindi')).toBe(true)
    expect(matchesSearch('Mrs. Kamini Chandra Hindi Grade 4', 'kamini maths')).toBe(false)
  })

  it('shows everything, alphabetically, for an empty search', () => {
    expect(rankMatches(staff, '  ').map((t) => t.name)).toEqual(['Pravin', 'Raghav', 'Mrs. Rao', 'Mr. Vikram', 'Vinita'])
  })
})
