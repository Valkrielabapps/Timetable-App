import React from 'react'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConstraintsTab from './ConstraintsTab'

vi.mock('../api', () => ({ api: {} }))
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 5, status: 'draft' }] }),
  useTimetable: () => ({
    data: {
      id: 5, status: 'draft', entries: [],
      violations: [{ constraint_id: 1, entry_ids: [], description: 'Old rule', detail: '' }],
      pending_constraint_ids: [2],
    },
  }),
}))

const rule = (id, description) => ({
  id, school_id: 1, type: 'ir', parameters: {}, is_hard: true, weight: 1, description,
  enforced: true, conflicts: [], about: null,
})

describe('rules added after the current timetable', () => {
  it('are tagged to generate again, while a real break stays under Needs attention', () => {
    render(
      <ConstraintsTab schoolId={1} classGroups={[]} onReload={vi.fn()}
        constraints={[rule(1, 'Old rule'), rule(2, 'New rule')]} />,
    )
    expect(screen.getByText(/1 rule was added after the current timetable/i)).toBeInTheDocument()
    expect(screen.getByText('New - generate again to apply')).toBeInTheDocument()
    const attention = screen.getByRole('region', { name: 'Needs attention' })
    expect(within(attention).getByText('Old rule')).toBeInTheDocument()
    expect(within(attention).queryByText('New rule')).toBeNull()
  })
})
