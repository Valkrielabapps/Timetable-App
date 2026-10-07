import React from 'react'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ConstraintsTab from './ConstraintsTab'

vi.mock('../api', () => ({ api: { reparseConstraint: vi.fn() } }))

const hooks = vi.hoisted(() => ({ timetable: null }))
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: hooks.timetable ? [{ id: hooks.timetable.id, status: 'draft' }] : [] }),
  useTimetable: () => ({ data: hooks.timetable }),
}))

/**
 * The saved rules, organised.
 *
 * Grouped by who each rule is about, with anything needing a fix at the top,
 * and searchable. Each rule's own sentence is its title - not its internal
 * type, which for most rules used to read "ir".
 */

let nextId = 1
const rule = (description, about = {}, extra = {}) => ({
  id: nextId++,
  type: 'ir',
  parameters: {},
  description,
  enforced: true,
  conflicts: [],
  is_hard: true,
  about: { teachers: [], subjects: [], class_groups: [], every: [], ...about },
  ...extra,
})

function renderList(constraints, { readOnly = false } = {}) {
  render(
    <ConstraintsTab
      schoolId={1}
      classGroups={[]}
      constraints={constraints}
      onReload={vi.fn()}
      readOnly={readOnly}
    />,
  )
}

const section = (name) => screen.getByRole('region', { name })

beforeEach(() => {
  hooks.timetable = null
})

describe('the saved rules, grouped', () => {
  it('groups rules under who they are about', () => {
    renderList([
      rule('Mrs. Rao is free on Fridays.', { teachers: ['Mrs. Rao'] }),
      rule('No PE in period 1.', { subjects: ['PE'] }),
      rule('School ends at period 8.'),
    ])
    expect(within(section('Teachers')).getByText('Mrs. Rao is free on Fridays.')).toBeInTheDocument()
    expect(within(section('Subjects')).getByText('No PE in period 1.')).toBeInTheDocument()
    expect(within(section('Whole school')).getByText('School ends at period 8.')).toBeInTheDocument()
  })

  it('does not title rules with their internal type', () => {
    renderList([rule('No PE in period 1.', { subjects: ['PE'] })])
    expect(screen.queryByText(/^ir$/i)).toBeNull()
  })

  it('names each group and how many rules it holds', () => {
    renderList([
      rule('One.', { teachers: ['Mrs. Rao'] }),
      rule('Two.', { teachers: ['Mrs. Rao'] }),
    ])
    expect(within(section('Teachers')).getByRole('button', { name: /Mrs\. Rao\s*2 rules/ })).toBeInTheDocument()
  })

  it('starts a long list with its groups closed', () => {
    const many = Array.from({ length: 13 }, (_, i) => rule(`Rule ${i}.`, { teachers: ['Mrs. Rao'] }))
    renderList(many)
    expect(screen.queryByText('Rule 0.')).toBeNull()
    fireEvent.click(within(section('Teachers')).getByRole('button', { name: /Mrs\. Rao/ }))
    expect(screen.getByText('Rule 0.')).toBeInTheDocument()
  })

  it('starts a short list open', () => {
    renderList([rule('Mrs. Rao is free on Fridays.', { teachers: ['Mrs. Rao'] })])
    expect(screen.getByText('Mrs. Rao is free on Fridays.')).toBeInTheDocument()
  })
})

describe('needs attention', () => {
  it('lists a rule that is not applied at the top, and not again below', () => {
    renderList([
      rule('Mrs. Rao is free on Fridays.', { teachers: ['Mrs. Rao'] }, { enforced: false }),
      rule('No PE in period 1.', { subjects: ['PE'] }),
    ])
    const attention = section('Needs attention')
    expect(within(attention).getByText('Mrs. Rao is free on Fridays.')).toBeInTheDocument()
    expect(within(attention).getByText('Not applied when generating')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Teachers' })).toBeNull()
  })

  it('lists a rule the current timetable breaks', () => {
    const pe = rule('No PE in period 1.', { subjects: ['PE'] })
    hooks.timetable = {
      id: 4, status: 'draft', entries: [],
      violations: [{ constraint_id: pe.id, description: pe.description, entry_ids: [], detail: 'x' }],
    }
    renderList([pe])
    expect(within(section('Needs attention')).getByText('Broken by the current timetable')).toBeInTheDocument()
  })

  it('ignores violations from a timetable still being generated', () => {
    const pe = rule('No PE in period 1.', { subjects: ['PE'] })
    hooks.timetable = {
      id: 4, status: 'generating', entries: [],
      violations: [{ constraint_id: pe.id, description: pe.description, entry_ids: [], detail: 'x' }],
    }
    renderList([pe])
    expect(screen.queryByRole('region', { name: 'Needs attention' })).toBeNull()
  })

  it('is not shown when nothing needs attention', () => {
    renderList([rule('No PE in period 1.', { subjects: ['PE'] })])
    expect(screen.queryByRole('region', { name: 'Needs attention' })).toBeNull()
  })
})

describe('searching and filtering', () => {
  const RULES = () => [
    rule('Mrs. Rao is free on Fridays.', { teachers: ['Mrs. Rao'] }),
    rule('No PE in period 1.', { subjects: ['PE'] }, { is_hard: false }),
    ...Array.from({ length: 12 }, (_, i) => rule(`Filler ${i}.`, { teachers: ['Mr. Khan'] })),
  ]

  it('shows only what matches, opened up', () => {
    renderList(RULES())
    fireEvent.change(screen.getByLabelText('Search rules'), { target: { value: 'fridays' } })
    // Long list, so groups start closed - a match must still be visible.
    expect(screen.getByText('Mrs. Rao is free on Fridays.')).toBeInTheDocument()
    expect(screen.queryByText('No PE in period 1.')).toBeNull()
    expect(screen.getByText('1 of 14 rules')).toBeInTheDocument()
  })

  it('filters by teacher', () => {
    renderList(RULES())
    fireEvent.change(screen.getByLabelText('Filter by teacher'), { target: { value: 'Mrs. Rao' } })
    expect(screen.getByText('Mrs. Rao is free on Fridays.')).toBeInTheDocument()
    expect(screen.queryByText('Filler 0.')).toBeNull()
  })

  it('shows only preferences', () => {
    renderList(RULES())
    fireEvent.click(screen.getByRole('button', { name: 'Preferences' }))
    expect(screen.getByText('No PE in period 1.')).toBeInTheDocument()
    expect(screen.queryByText('Mrs. Rao is free on Fridays.')).toBeNull()
  })

  it('says when nothing matches', () => {
    renderList(RULES())
    fireEvent.change(screen.getByLabelText('Search rules'), { target: { value: 'zzz' } })
    expect(screen.getByText('No rules match.')).toBeInTheDocument()
  })

  it('clears back to everything', () => {
    renderList(RULES())
    fireEvent.change(screen.getByLabelText('Search rules'), { target: { value: 'zzz' } })
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByText('14 rules')).toBeInTheDocument()
  })
})

describe('editing a rule listed twice', () => {
  it('opens only the copy that was clicked', () => {
    // A rule about two teachers appears under both.
    renderList([rule('Mrs. Rao and Mr. Khan never overlap.', { teachers: ['Mr. Khan', 'Mrs. Rao'] })])
    expect(screen.getAllByText('Mrs. Rao and Mr. Khan never overlap.')).toHaveLength(2)
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit constraint' })[0])
    expect(screen.getAllByRole('textbox', { name: '' }).filter((el) => el.tagName === 'TEXTAREA')).toHaveLength(1)
  })
})
