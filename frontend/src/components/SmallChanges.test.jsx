import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ replaceTeacher: vi.fn() }))
vi.mock('../api', () => ({ api }))
import ReplaceTeacherDialog from './ReplaceTeacherDialog'
import { PlanChangedBar } from './TimetableTab'

const TEACHERS = [{ id: 1, name: 'Anil' }, { id: 2, name: 'Ravi' }]
const SECTIONS = [{ id: 5, grade: 'Grade 6', name: 'A' }, { id: 6, grade: 'Grade 6', name: 'B' }]
const ENTRIES = [
  { teacher_id: 1, class_group_id: 5 }, { teacher_id: 1, class_group_id: 5 }, { teacher_id: 1, class_group_id: 6 },
]

describe('small changes', () => {
  it('replaces a teacher in some sections, then offers to place the clashes', async () => {
    api.replaceTeacher.mockResolvedValue({ swapped: 1, left: 1, plan: 1, changes: [] })
    const onUpdate = vi.fn()
    render(<ReplaceTeacherDialog schoolId={9} teachers={TEACHERS} classGroups={SECTIONS} entries={ENTRIES}
      onClose={() => {}} onDone={() => {}} onUpdate={onUpdate} />)
    const [from, to] = screen.getAllByRole('combobox')
    fireEvent.change(from, { target: { value: '1' } })
    expect(screen.getByText('3 lessons a week in this timetable')).toBeInTheDocument()
    fireEvent.change(to, { target: { value: '2' } })
    fireEvent.click(screen.getByLabelText('Only some sections'))
    expect(screen.getByRole('button', { name: 'Replace' })).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Grade 6 A'))
    fireEvent.click(screen.getByRole('button', { name: 'Replace' }))
    await waitFor(() => expect(api.replaceTeacher).toHaveBeenCalledWith({
      school_id: 9, from_teacher_id: 1, to_teacher_id: 2, class_group_ids: [5] }))
    expect(await screen.findByRole('status')).toHaveTextContent('Ravi took 1 of Anil’s lessons at the same times')
    fireEvent.click(screen.getByRole('button', { name: 'Update the timetable' }))
    expect(onUpdate).toHaveBeenCalled()
  })

  it('shows what changed in the plan and offers the update', () => {
    const onUpdate = vi.fn()
    const changes = [1, 2, 3, 4].map((n) => ({ text: `Grade 6 A: change ${n}` }))
    render(<PlanChangedBar changes={changes} onUpdate={onUpdate} busy={false} />)
    expect(screen.getByText('The plan has changed since this timetable was made')).toBeInTheDocument()
    expect(screen.queryByText('Grade 6 A: change 4')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'and 1 more' }))
    expect(screen.getByText('Grade 6 A: change 4')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Update the timetable' }))
    expect(onUpdate).toHaveBeenCalled()
  })

  it('says what an update kept', () => {
    render(<PlanChangedBar changes={[]} update={{ stage: 1, unchanged: 46, placed: 1 }} onUpdate={() => {}} />)
    expect(screen.getByRole('status')).toHaveTextContent('46 lessons stayed exactly where they were and 1 was placed')
  })
})
