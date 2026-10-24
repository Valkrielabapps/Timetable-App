import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'

vi.mock('../api', () => ({ api: {} }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: undefined }) }))

const mockTimetable = vi.fn()
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 1, status: 'draft' }] }),
  useTimetable: () => ({ data: mockTimetable() }),
  useGenerateTimetable: () => ({ generate: vi.fn(), isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useOptimisticSlotMove: () => vi.fn(),
  useFrozenStatus: () => ({ data: [] }),
  useSetFrozen: () => ({ setFrozen: vi.fn(), isSaving: false }),
  useElectiveBlocks: () => ({ data: [] }),
}))

/** A subject nobody can teach yet is placed anyway, and the page says so. */

const PERIODS = [
  { id: 1, day_of_week: 0, order: 0, label: null, is_break: false },
  { id: 2, day_of_week: 0, order: 1, label: null, is_break: false },
]

const base = {
  class_group_id: 100, class_group_name: 'A', assistant_teacher_id: null, assistant_teacher_name: null,
  period_label: null, day_of_week: 0, room_id: null, room_name: null, locked: false, lab_batch: null,
}
const ENGLISH = { ...base, id: 11, subject_id: 1, subject_name: 'English', teacher_id: 10, teacher_name: 'Mrs. Rao', period_id: 1, order: 0 }
const ASSEMBLY = { ...base, id: 12, subject_id: 2, subject_name: 'Assembly', teacher_id: null, teacher_name: null, period_id: 2, order: 1 }

function renderTab(entries) {
  mockTimetable.mockReturnValue({ id: 1, status: 'draft', entries, violations: [] })
  render(
    <TimetableTab
      schoolId={1}
      classGroup={{ id: 100, grade: 'Grade 8', name: 'A' }}
      classGroups={[{ id: 100, grade: 'Grade 8', name: 'A' }]}
      teachers={[{ id: 10, name: 'Mrs. Rao' }]}
      periods={PERIODS}
      constraints={[]}
      readOnly
    />,
  )
}

describe('lessons with no teacher yet', () => {
  it('marks the lesson and lists the subject', () => {
    renderTab([ENGLISH, ASSEMBLY])
    expect(screen.getByText('1 subject has no teacher yet')).toBeInTheDocument()
    expect(screen.getByText(/Assembly in Grade 8 - A/)).toBeInTheDocument()
    expect(screen.getAllByText('No teacher yet').length).toBeGreaterThan(0)
  })

  it('says nothing when every lesson has a teacher', () => {
    renderTab([ENGLISH])
    expect(screen.queryByText(/no teacher yet/i)).not.toBeInTheDocument()
  })
})
