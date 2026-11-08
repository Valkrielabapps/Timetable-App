import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ api: { setupCheck: vi.fn(() => Promise.resolve({ errors: [], warnings: [] })) } }))
vi.mock('./TimetableStructurePanel', () => ({ default: () => <div>Week builder</div> }))
vi.mock('./BulkAddClassGroups', () => ({ default: () => <div>Add sections</div> }))
vi.mock('./BulkImportPanel', () => ({
  default: ({ resource, onFileRead }) => (
    <button onClick={() => onFileRead(new File(['x'], 'allotment.xlsx'))}>Upload {resource}</button>
  ),
}))
vi.mock('./StandardRules', () => ({ default: () => <div>Common rules</div> }))
vi.mock('./SetupCheckPanel', () => ({ default: () => <div>Setup check</div> }))
vi.mock('./ClassPlanImport', () => ({ default: ({ file }) => <div>Plans from file {file ? file.name : 'none'}</div> }))
import GetStartedTab from './GetStartedTab'

const SCHOOL = { id: 1, name: 'Sunrise', institution_type: 'school', standard_rules: null }
const lesson = (id) => ({ id, kind: 'lesson' })

function setup(props = {}) {
  const handlers = { onOpenSection: vi.fn(), onOpenTab: vi.fn(), onGenerate: vi.fn(), onReload: vi.fn() }
  render(<GetStartedTab school={SCHOOL} {...handlers} {...props} />)
  return handlers
}

describe('Get started', () => {
  it('opens on the first thing still to do, in plain words', () => {
    setup()
    expect(screen.getByRole('button', { name: /Your school day/, expanded: true })).toBeInTheDocument()
    expect(screen.getByText('Week builder')).toBeInTheDocument()
    expect(screen.getByText(/Six steps from here to a finished timetable/)).toBeInTheDocument()
    // Next opens the next step.
    fireEvent.click(screen.getByRole('button', { name: 'Skip for now' }))
    expect(screen.getByText('Add sections')).toBeInTheDocument()
  })

  it('skips to the staff upload when the day and classes are done', () => {
    setup({ periods: [lesson(1), lesson(2), { id: 3, kind: 'break' }], classGroups: [{ id: 5, grade: 'Grade 6', name: 'A' }] })
    expect(screen.getByText('Upload teachers')).toBeInTheDocument()
    expect(screen.getByText('2 lessons a week')).toBeInTheDocument()
    // The staff sheet goes on to step 4, for every class's plan.
    fireEvent.click(screen.getByText('Upload teachers'))
    fireEvent.click(screen.getByRole('button', { name: 'Skip for now' }))
    expect(screen.getByText('Plans from file allotment.xlsx')).toBeInTheDocument()
  })

  it('lists every section’s plan and opens one to fill in', () => {
    const h = setup({
      periods: [lesson(1), lesson(2)],
      classGroups: [{ id: 5, grade: 'Grade 6', name: 'A' }, { id: 6, grade: 'Grade 6', name: 'B' }],
      teachers: [{ id: 1 }], subjects: [{ id: 1 }],
      allRequirements: [{ class_group_id: 5, periods_per_week: 2 }],
    })
    expect(screen.getByText('1 subjects, 2 of 2 periods')).toBeInTheDocument()
    expect(screen.getByText('Nothing yet')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Fill in' }))
    expect(h.onOpenSection).toHaveBeenCalledWith(6, 'plan')
  })

  it('builds the timetable once everything needed is there', async () => {
    const h = setup({
      periods: [lesson(1)],
      classGroups: [{ id: 5, grade: 'Grade 6', name: 'A' }],
      teachers: [{ id: 1 }], subjects: [{ id: 1 }],
      allRequirements: [{ class_group_id: 5, periods_per_week: 1 }],
    })
    expect(await screen.findByText('Setup check')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Build my timetable' }))
    expect(h.onGenerate).toHaveBeenCalled()
  })

  it('won’t build while a required step is missing', async () => {
    setup({ periods: [lesson(1)] })
    fireEvent.click(screen.getByRole('button', { name: /Build the timetable/ }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Build my timetable' })).toBeDisabled())
    expect(screen.getByText(/Still to do: your classes, your teachers and subjects, what each class needs/)).toBeInTheDocument()
  })
})
