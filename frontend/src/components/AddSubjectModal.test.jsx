import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ api: { bulkImportTemplateUrl: () => '#' } }))
import SubjectsSection from './SubjectsSection'

const SUBJECTS = [{ id: 1, name: 'Maths' }]
const TEACHERS = [
  { id: 10, name: 'Priya', qualified_subject_ids: [1] },
  { id: 11, name: 'Anil', qualified_subject_ids: [] },
]

function setup() {
  const subjectsApi = { create: vi.fn().mockResolvedValue({ id: 5, name: 'Robotics' }), update: vi.fn(), delete: vi.fn(), reload: vi.fn() }
  const teachersApi = { update: vi.fn().mockResolvedValue(undefined) }
  render(<SubjectsSection schoolId={3} subjects={SUBJECTS} teachers={TEACHERS}
    onSubjectsChanged={subjectsApi} onTeachersChanged={teachersApi} />)
  return { subjectsApi, teachersApi }
}

describe('Add subject box', () => {
  it('opens like Add teacher and adds the subject with its teachers and room', async () => {
    const { subjectsApi, teachersApi } = setup()
    fireEvent.click(screen.getByRole('button', { name: '+ Add subject' }))
    expect(screen.getByRole('dialog', { name: 'Add subject' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Robotics' } })
    fireEvent.click(screen.getByLabelText('Priya'))
    fireEvent.change(screen.getByLabelText(/Room it needs/), { target: { value: 'lab' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add subject' }))

    await waitFor(() => expect(subjectsApi.create).toHaveBeenCalledWith(
      { school_id: 3, name: 'Robotics', required_room_type: 'lab' }))
    // Priya keeps Maths and gains Robotics; Anil wasn't ticked.
    await waitFor(() => expect(teachersApi.update).toHaveBeenCalledWith(10, { qualified_subject_ids: [1, 5] }))
    expect(teachersApi.update).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it("won't add a second subject with the same name", () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '+ Add subject' }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: ' maths ' } })
    expect(screen.getByText("There's already a subject called that.")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add subject' })).toBeDisabled()
  })
})
