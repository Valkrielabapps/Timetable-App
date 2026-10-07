import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TeachersSection from './TeachersSection'

vi.mock('../api', () => ({ api: {} }))

const hooks = vi.hoisted(() => ({ blocks: [] }))
vi.mock('../hooks/useSchoolData', () => ({
  useElectiveBlocks: () => ({ data: hooks.blocks }),
}))

/**
 * A teacher's planned load counts the block options pinned to them.
 *
 * An option runs in every one of its block's periods, so Mrs. Rao pinned to
 * Physics in a six-period block teaches six periods - which the overload
 * warning has to know about before anything is generated.
 */

const TEACHER = {
  id: 10, name: 'Mrs. Rao', qualified_subject_ids: [1, 4], qualified_grades: [],
  max_periods_per_week: null, unavailable_period_ids: [], is_assistant_eligible: false,
}

function renderTeachers(blocks) {
  hooks.blocks = blocks
  render(
    <TeachersSection
      schoolId={1}
      teachers={[TEACHER]}
      subjects={[{ id: 1, name: 'Physics' }, { id: 2, name: 'Accounts' }, { id: 4, name: 'English' }]}
      classGroups={[{ id: 100, grade: 'Grade 11', name: 'A' }]}
      allRequirements={[
        { id: 1, class_group_id: 100, subject_id: 4, periods_per_week: 5, preferred_teacher_id: 10 },
      ]}
      onTeachersChanged={{ create: vi.fn(), update: vi.fn(), delete: vi.fn(), reload: vi.fn() }}
      readOnly
    />,
  )
}

const BLOCK = (teacherId) => ({
  id: 7, school_id: 1, class_group_id: 100, name: 'Block 1', periods_per_week: 6,
  options: [{ id: 70, subject_id: 1, preferred_teacher_id: teacherId },
            { id: 71, subject_id: 2, preferred_teacher_id: null }],
})

describe('teacher workload with elective blocks', () => {
  it('adds the periods of a block option pinned to them', () => {
    renderTeachers([BLOCK(10)])
    expect(screen.getByText('11 periods/week')).toBeInTheDocument()
  })

  it('leaves out options pinned to someone else, or to nobody', () => {
    renderTeachers([BLOCK(99)])
    expect(screen.getByText('5 periods/week')).toBeInTheDocument()
  })
})
