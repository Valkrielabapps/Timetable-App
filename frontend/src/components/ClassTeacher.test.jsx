import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { optionsOf, pick } from '../test/pick'
import DataEntryTab from './DataEntryTab'
import TeachersSection from './TeachersSection'

const api = vi.hoisted(() => ({ updateClassGroup: vi.fn() }))
vi.mock('../api', () => ({ api }))
vi.mock('../hooks/useSchoolData', () => ({
  useRooms: () => ({ data: [] }),
  useRoomMutations: () => ({ create: vi.fn(), delete: vi.fn() }),
  useElectiveBlocks: () => ({ data: [] }),
  useElectiveBlockMutations: () => ({ create: vi.fn(), update: vi.fn(), delete: vi.fn(), invalidate: vi.fn() }),
  useTimetables: () => ({ data: [] }),
  useTimetable: () => ({ data: null }),
}))

/**
 * Each section's class teacher: the teacher with them in the class teacher
 * period. Set on the section's plan; shown on the Teachers page.
 */

const TEACHERS = [
  { id: 10, name: 'Mrs. Rao', qualified_subject_ids: [], qualified_grades: [], unavailable_period_ids: [] },
  { id: 11, name: 'Mr. Khan', qualified_subject_ids: [], qualified_grades: [], unavailable_period_ids: [] },
]

function renderPlan(classGroups, setClassGroups = vi.fn()) {
  render(
    <DataEntryTab
      schoolId={1}
      classGroupId={100}
      subjects={[{ id: 1, name: 'English' }]}
      setSubjects={vi.fn()}
      teachers={TEACHERS}
      setTeachers={vi.fn()}
      periods={[{ id: 1, day_of_week: 0, order: 0 }]}
      setPeriods={vi.fn()}
      classGroups={classGroups}
      setClassGroups={setClassGroups}
      allRequirements={[{ id: 1, class_group_id: 100, subject_id: 1, periods_per_week: 5, preferred_teacher_id: null }]}
      setAllRequirements={vi.fn()}
      onReloadSchoolData={vi.fn()}
      subView="plan"
      onSubViewChange={vi.fn()}
    />,
  )
  return setClassGroups
}

beforeEach(() => vi.clearAllMocks())

describe('class teacher', () => {
  it("is chosen on the section's plan", async () => {
    const updated = { id: 100, grade: 'Grade 6', name: 'A', class_teacher_id: 10 }
    api.updateClassGroup.mockResolvedValue(updated)
    const setClassGroups = renderPlan([{ id: 100, grade: 'Grade 6', name: 'A', class_teacher_id: null }])
    pick('Class teacher', 'Mrs. Rao')
    await waitFor(() => expect(api.updateClassGroup).toHaveBeenCalledWith(100, { class_teacher_id: 10 }))
    // Patched into the sections in place, not reloaded.
    const patch = setClassGroups.mock.calls[0][0]
    expect(patch([{ id: 100, class_teacher_id: null }, { id: 101 }])).toEqual([updated, { id: 101 }])
  })

  it('can be cleared', async () => {
    api.updateClassGroup.mockResolvedValue({ id: 100, class_teacher_id: null })
    renderPlan([{ id: 100, grade: 'Grade 6', name: 'A', class_teacher_id: 10 }])
    pick('Class teacher', 'Not set')
    await waitFor(() => expect(api.updateClassGroup).toHaveBeenCalledWith(100, { class_teacher_id: null }))
  })

  it('warns when the teacher is already class teacher of another section', () => {
    renderPlan([
      { id: 100, grade: 'Grade 6', name: 'A', class_teacher_id: 10 },
      { id: 101, grade: 'Grade 6', name: 'B', class_teacher_id: 10 },
    ])
    expect(screen.getByText(/Mrs. Rao is also class teacher of Grade 6 · B/)).toBeInTheDocument()
  })

  it('does not warn about a teacher with one section', () => {
    renderPlan([
      { id: 100, grade: 'Grade 6', name: 'A', class_teacher_id: 10 },
      { id: 101, grade: 'Grade 6', name: 'B', class_teacher_id: 11 },
    ])
    expect(screen.queryByText(/is also class teacher/)).toBeNull()
  })

  it('is shown on the Teachers page', () => {
    render(
      <TeachersSection
        schoolId={1}
        teachers={TEACHERS}
        subjects={[]}
        classGroups={[
          { id: 100, grade: 'Grade 6', name: 'A', class_teacher_id: 10 },
          { id: 101, grade: 'Grade 6', name: 'B', class_teacher_id: 11 },
        ]}
        allRequirements={[]}
        onTeachersChanged={{ create: vi.fn(), update: vi.fn(), delete: vi.fn(), reload: vi.fn() }}
        readOnly
      />,
    )
    // Each teacher shows their own section, and only theirs.
    expect(screen.getAllByText('Class teacher · Grade 6 A')).toHaveLength(1)
    expect(screen.getAllByText('Class teacher · Grade 6 B')).toHaveLength(1)
  })
})
