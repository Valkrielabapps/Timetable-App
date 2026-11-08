import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ classPlanPreview: vi.fn(), classPlanCommit: vi.fn() }))
vi.mock('../api', () => ({ api }))
import ClassPlanImport from './ClassPlanImport'

const PREVIEW = {
  summary: { classes: 2, sections: 2, subjects: 3 },
  lessons_per_week: 40,
  skipped: ['Assembly (Class 3)'],
  new_subjects: ['Civics'],
  checks: ['Anil is planned for 60 periods a week, more than the 40 lessons in your week.'],
  plan: {
    tables: [
      { id: 't0', label: 'Class 3', grade: 'Grade 3', sections: [], sections_q: 'sections:all', items: [{ id: 't0.0', raw: 'Maths', periods: 6, teachers: ['Anil'] }] },
      { id: 't1', label: 'CLASS 6-AB', grade: 'Grade 6', sections: ['A', 'B'], items: [{ id: 't1.0', raw: 'Maths', periods: 6, teachers: ['Muthu', 'Vivek'] }] },
    ],
    people: {},
  },
  questions: [
    { id: 'sections:all', text: 'These classes don’t say which sections they are for: Class 3.', options: [{ key: 'n:1', label: 'One each (A)' }, { key: 'n:2', label: 'Two each (A and B)' }], suggested: 'n:1' },
    { id: 'shared:all', text: 'Does each teacher take one section, in order?', options: [{ key: 'order', label: 'Yes' }, { key: 'either', label: 'No' }], suggested: 'order' },
  ],
}

describe('filling in every class from the allotment sheet', () => {
  it('reads the file from step 3, asks, and saves only once everything is answered', async () => {
    api.classPlanPreview.mockResolvedValue(PREVIEW)
    api.classPlanCommit.mockResolvedValue({ sections: ['Grade 3 A', 'Grade 6 A', 'Grade 6 B'], subjects: ['Civics'], teachers: [], requirements: 3, blocks: 0 })
    const onDone = vi.fn()
    const file = new File(['x'], 'allotment.xlsx')
    render(<ClassPlanImport schoolId={1} file={file} onDone={onDone} />)
    expect(await screen.findByText(/We found plans for/)).toHaveTextContent('2 classes')
    expect(api.classPlanPreview).toHaveBeenCalledWith(1, file)
    expect(screen.getByText(/Fix these first/)).toBeInTheDocument()
    expect(screen.getByText(/Left out because they have 0 periods: Assembly/)).toBeInTheDocument()

    const go = screen.getByRole('button', { name: 'Answer 2 questions to fill in the plans' })
    expect(go).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/Two each/))
    expect(screen.getByRole('button', { name: 'Answer the question to fill in the plans' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Use the suggested answers' }))
    fireEvent.click(screen.getByRole('button', { name: 'Fill in the plans' }))
    await waitFor(() => expect(api.classPlanCommit).toHaveBeenCalledWith(1, PREVIEW.plan, { 'sections:all': 'n:1', 'shared:all': 'order' }))
    expect(await screen.findByRole('status')).toHaveTextContent('3 new sections, 3 subject plans, 1 new subjects')
    expect(onDone).toHaveBeenCalled()
  })

  it('says why a file can’t be used', async () => {
    api.classPlanPreview.mockRejectedValue(new Error('Couldn’t find a table for each class in this file.'))
    render(<ClassPlanImport schoolId={1} file={new File(['x'], 'staff.csv')} />)
    expect(await screen.findByText(/Couldn’t find a table for each class/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Read file' })).toBeInTheDocument()
  })
})
