import React from 'react'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import DataEntryTab from './DataEntryTab'

vi.mock('../api', () => ({ api: {} }))

const hooks = vi.hoisted(() => ({ blocks: [] }))
vi.mock('../hooks/useSchoolData', () => ({
  useRooms: () => ({ data: [] }),
  useRoomMutations: () => ({ create: vi.fn(), delete: vi.fn() }),
  useElectiveBlocks: () => ({ data: hooks.blocks }),
  useElectiveBlockMutations: () => ({
    create: vi.fn(), update: vi.fn(), delete: vi.fn(), invalidate: vi.fn(),
  }),
}))

/**
 * Elective blocks on a section's plan.
 *
 * A subject is either one everybody in the section takes or an option in a
 * block - never both, which the server refuses. The plan page shows where each
 * subject is so the refusal never has to happen, and counts a block once
 * towards the week, since all its options share the same periods.
 */

const SUBJECTS = [
  { id: 1, name: 'Physics' },
  { id: 2, name: 'Accounts' },
  { id: 4, name: 'English' },
]

const BLOCKS = [
  { id: 7, school_id: 1, class_group_id: 100, name: 'Block 1', periods_per_week: 6,
    options: [{ id: 70, subject_id: 1, preferred_teacher_id: null },
              { id: 71, subject_id: 2, preferred_teacher_id: null }] },
  // Another section's block: none of this section's business.
  { id: 8, school_id: 1, class_group_id: 101, name: 'Block 9', periods_per_week: 4,
    options: [{ id: 80, subject_id: 4, preferred_teacher_id: null },
              { id: 81, subject_id: 2, preferred_teacher_id: null }] },
]

function renderPlan(blocks = BLOCKS) {
  hooks.blocks = blocks
  render(
    <DataEntryTab
      schoolId={1}
      classGroupId={100}
      subjects={SUBJECTS}
      setSubjects={vi.fn()}
      teachers={[]}
      setTeachers={vi.fn()}
      periods={[{ id: 1, day_of_week: 0, order: 0 }]}
      setPeriods={vi.fn()}
      classGroups={[{ id: 100, grade: 'Grade 11', name: 'A' }, { id: 101, grade: 'Grade 12', name: 'A' }]}
      allRequirements={[
        { id: 1, class_group_id: 100, subject_id: 4, periods_per_week: 5, preferred_teacher_id: null },
      ]}
      setAllRequirements={vi.fn()}
      onReloadSchoolData={vi.fn()}
      subView="plan"
      onSubViewChange={vi.fn()}
    />,
  )
}

describe("a section's plan with elective blocks", () => {
  it('counts each block once towards the week', () => {
    // English 5 + Block 1's 6. Not 5 + 6 + 6 for two options, and not the
    // other section's block.
    renderPlan()
    // In the summary above the table and in its Total row.
    expect(screen.getAllByText('11')).toHaveLength(2)
  })

  it('shows the section’s blocks under its subjects', () => {
    renderPlan()
    expect(screen.getByText('Elective blocks')).toBeInTheDocument()
    // Once as a row in the subjects table (to tick and copy), once in the
    // block editor below it.
    expect(screen.getAllByText('Block 1')).toHaveLength(2)
    expect(screen.queryByText('Block 9')).toBeNull()
  })

  it('lists each block as a row with its own tick box, for copying', () => {
    renderPlan()
    const box = screen.getByRole('checkbox', { name: 'Select Block 1' })
    expect(box).not.toBeChecked()
    fireEvent.click(box)
    expect(box).toBeChecked()
    expect(screen.getAllByText('Elective block').length).toBeGreaterThan(0)
  })

  it('can also make a block option a subject everyone takes, saying where else it is', () => {
    // English for everyone plus an English option in a block are separate lessons.
    renderPlan()
    fireEvent.click(screen.getByText('Edit subjects'))
    const physics = screen.getByText('Physics').closest('label')
    expect(within(physics).getByRole('checkbox')).toBeEnabled()
    expect(physics).toHaveTextContent('also in Block 1')
  })

  it("still offers subjects that are only in another section's block", () => {
    renderPlan()
    fireEvent.click(screen.getByText('Edit subjects'))
    // Accounts is in this section's block; English is in 12A's, and is
    // already one this section takes - so it stays checked and enabled.
    const english = screen.getByText('English').closest('label')
    expect(within(english).getByRole('checkbox')).toBeEnabled()
    expect(english).not.toHaveTextContent('Block')
  })
})

describe("picking a section's subjects", () => {
  it('lists them alphabetically and narrows them as you type', () => {
    renderPlan([])
    fireEvent.click(screen.getByText('Edit subjects'))
    const listed = () => screen.getAllByRole('checkbox').map((c) => c.closest('label').firstChild.nextSibling.textContent)
    expect(listed()).toEqual(['Accounts', 'English', 'Physics'])
    fireEvent.change(screen.getByLabelText('Search subjects'), { target: { value: 'phy' } })
    expect(listed()).toEqual(['Physics'])
  })
})
