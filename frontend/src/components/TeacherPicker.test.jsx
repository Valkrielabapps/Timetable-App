import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import DataEntryTab from './DataEntryTab'

const api = vi.hoisted(() => ({ updateRequirement: vi.fn() }))
vi.mock('../api', () => ({ api }))
vi.mock('../hooks/useSchoolData', () => ({
  useRooms: () => ({ data: [] }),
  useRoomMutations: () => ({ create: vi.fn(), delete: vi.fn() }),
  useElectiveBlocks: () => ({ data: [] }),
  useElectiveBlockMutations: () => ({ create: vi.fn(), update: vi.fn(), delete: vi.fn(), invalidate: vi.fn() }),
}))

const TEACHERS = ['Priya', 'Joseph', 'Anita'].map((name, i) => ({
  id: i + 1, name, qualified_subject_ids: [4], qualified_grades: [], is_assistant_eligible: false,
}))

function renderPlan(requirement) {
  render(
    <DataEntryTab
      schoolId={1}
      classGroupId={100}
      subjects={[{ id: 4, name: 'English' }]}
      setSubjects={vi.fn()}
      teachers={TEACHERS}
      setTeachers={vi.fn()}
      periods={[{ id: 1, day_of_week: 0, order: 0 }]}
      setPeriods={vi.fn()}
      classGroups={[{ id: 100, grade: 'Grade 9', name: 'A' }]}
      allRequirements={[{ id: 1, class_group_id: 100, subject_id: 4, periods_per_week: 6, preferred_teacher_id: null, ...requirement }]}
      setAllRequirements={vi.fn()}
      onReloadSchoolData={vi.fn()}
      subView="plan"
      onSubViewChange={vi.fn()}
    />,
  )
}

const pickerButton = () => screen.getByRole('button', { name: /teachers for english/i })

describe('choosing teachers for a subject', () => {
  beforeEach(() => {
    api.updateRequirement.mockReset()
    api.updateRequirement.mockImplementation(async (id, data) => ({ id, ...data }))
  })

  it('saves several ticked teachers as a shortlist, in one request', async () => {
    renderPlan()
    expect(pickerButton()).toHaveTextContent('Any (let solver choose)')
    fireEvent.click(pickerButton())
    fireEvent.click(screen.getByRole('checkbox', { name: 'Priya' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Joseph' }))
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(api.updateRequirement).toHaveBeenCalledTimes(1))
    expect(api.updateRequirement).toHaveBeenCalledWith(1, { preferred_teacher_id: null, allowed_teacher_ids: [1, 2] })
  })

  it('saves one ticked teacher as the fixed teacher', async () => {
    renderPlan()
    fireEvent.click(pickerButton())
    fireEvent.click(screen.getByRole('checkbox', { name: 'Anita' }))
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() =>
      expect(api.updateRequirement).toHaveBeenCalledWith(1, { preferred_teacher_id: 3, allowed_teacher_ids: null }),
    )
  })

  it('shows an existing shortlist and can clear it back to any teacher', async () => {
    renderPlan({ allowed_teacher_ids: [1, 2] })
    expect(pickerButton()).toHaveTextContent('2 teachers: Priya, Joseph')
    fireEvent.click(pickerButton())
    fireEvent.click(screen.getByRole('button', { name: /clear/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() =>
      expect(api.updateRequirement).toHaveBeenCalledWith(1, { preferred_teacher_id: null, allowed_teacher_ids: null }),
    )
  })

  it('saves nothing if nothing changed', () => {
    renderPlan({ preferred_teacher_id: 2 })
    expect(pickerButton()).toHaveTextContent('Joseph')
    fireEvent.click(pickerButton())
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(api.updateRequirement).not.toHaveBeenCalled()
  })
})
