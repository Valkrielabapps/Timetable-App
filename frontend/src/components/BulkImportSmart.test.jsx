import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BulkImportPanel from './BulkImportPanel'

const api = vi.hoisted(() => ({
  bulkImport: vi.fn(),
  bulkImportPreview: vi.fn(),
  bulkImportCommit: vi.fn(),
  bulkImportTemplateUrl: () => '#',
}))
vi.mock('../api', () => ({ api }))

const PREVIEW = {
  kind: 'teachers', total: 10, subject_count: 3, will_update: 1, sheet: 'Staff',
  read_as: ['“Name of Teacher” as teacher’s full name'],
  matched: ['“Maths” as Mathematics', '“Comp Sci” as Computer Science'],
  doubtful: ['“Comp Sci” as Computer Science'],
  checks: ['1 teacher has no subjects (Anil Kumar). They can’t be timetabled until they’re given some.'],
  new_subjects: ['Physics'],
  rows: [
    { name: 'Priya Sharma', qualified_subjects: 'Mathematics;Physics', qualified_grades: 'Grade 9', max_periods_per_week: '28' },
    ...Array.from({ length: 8 }, (_, i) => ({ name: `Teacher ${i}`, qualified_subjects: 'Mathematics' })),
    { name: 'Anil Kumar' },
  ],
  row_notes: [[], [], [], [], [], [], [], [], [], ['No subjects']],
}

function choose(container) {
  const input = container.querySelector('input[type="file"]')
  fireEvent.change(input, { target: { files: [new File(['x'], 'staff.xlsx')] } })
  fireEvent.click(screen.getByRole('button', { name: 'Read file' }))
}

describe('importing a school’s own staff list', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the sheet as it will be saved, and saves nothing until Import', async () => {
    api.bulkImportPreview.mockResolvedValue(PREVIEW)
    const { container } = render(<BulkImportPanel schoolId={1} resource="teachers" />)
    expect(screen.getByText(/in any layout/)).toBeInTheDocument()
    choose(container)
    const box = await screen.findByRole('region', { name: 'Check before importing' })
    expect(within(box).getByText(/We found 10 teachers and 3 subjects/)).toBeInTheDocument()
    expect(within(box).getByText('“Comp Sci” as Computer Science?').tagName).toBe('MARK')
    expect(within(box).getByText(/Worth checking/)).toBeInTheDocument()
    expect(within(box).getByText(/1 new subject will be added: Physics/)).toBeInTheDocument()
    // First eight rows, plus Anil's further down because he has a note.
    expect(within(box).getByText('Mathematics, Physics')).toBeInTheDocument()
    expect(within(box).getByText('No subjects').closest('tr')).toHaveClass('bg-amber-50')
    expect(within(box).queryByText('Teacher 7')).not.toBeInTheDocument()
    expect(within(box).getByText(/and 1 more row/)).toBeInTheDocument()
    expect(api.bulkImportCommit).not.toHaveBeenCalled()
    expect(api.bulkImport).not.toHaveBeenCalled()

    api.bulkImportCommit.mockResolvedValue({ created: 9, updated: 1, errors: [], new_subjects: ['Physics'] })
    const onImported = vi.fn()
    fireEvent.click(within(box).getByRole('button', { name: 'Import 10 teachers' }))
    await waitFor(() => expect(screen.getByText(/9 created, 1 updated/)).toBeInTheDocument())
    expect(api.bulkImportCommit).toHaveBeenCalledWith('teachers', 1, PREVIEW.rows)
    expect(screen.queryByRole('region', { name: 'Check before importing' })).not.toBeInTheDocument()
    expect(screen.getByText(/Added a new subject: Physics/)).toBeInTheDocument()
  })

  it('Cancel drops the preview without saving', async () => {
    api.bulkImportPreview.mockResolvedValue(PREVIEW)
    const { container } = render(<BulkImportPanel schoolId={1} resource="teachers" />)
    choose(container)
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('region', { name: 'Check before importing' })).not.toBeInTheDocument()
    expect(api.bulkImportCommit).not.toHaveBeenCalled()
  })

  it('takes a Word document and says which table it read', async () => {
    api.bulkImportPreview.mockResolvedValue({ ...PREVIEW, sheet: 'table 1 of the document' })
    const { container } = render(<BulkImportPanel schoolId={1} resource="teachers" />)
    expect(container.querySelector('input[type="file"]').getAttribute('accept')).toContain('.docx')
    expect(screen.getByText(/Word document/)).toBeInTheDocument()
    choose(container)
    expect(await screen.findByText(/From table 1 of the document, taking/)).toBeInTheDocument()
  })

  it('asks about look-alike names and imports the answered rows', async () => {
    api.bulkImportPreview.mockResolvedValue({
      ...PREVIEW, total: 3, row_notes: [[], [], []], checks: [],
      rows: [
        { name: 'Kavita K', qualified_subjects: 'Hindi' },
        { name: 'Kavita Khana', qualified_subjects: 'Hindi;Computer Science' },
        { name: 'Anil', qualified_subjects: 'Maths' },
      ],
      questions: [
        {
          id: 'teacher:Kavita K|Kavita Khana',
          text: 'Are “Kavita K” and “Kavita Khana” the same teacher?',
          options: [
            { label: 'Yes, call them “Kavita Khana”', edits: [{ row: 0, field: 'name', remove: ['Kavita K'], add: ['Kavita Khana'] }] },
            { label: 'Yes, call them “Kavita K”', edits: [{ row: 1, field: 'name', remove: ['Kavita Khana'], add: ['Kavita K'] }] },
            { label: 'No, two different teachers', edits: [] },
          ],
        },
        {
          id: 'meaning:Comp Sci',
          text: 'Is “Comp Sci” “Computer Science”?',
          options: [
            { label: 'Yes', edits: [] },
            { label: 'No, keep “Comp Sci” as its own subject', edits: [{ row: 1, field: 'qualified_subjects', remove: ['Computer Science'], add: ['Comp Sci'] }] },
          ],
        },
      ],
    })
    api.bulkImportCommit.mockResolvedValue({ created: 2, updated: 1, errors: [], new_subjects: [] })
    const { container } = render(<BulkImportPanel schoolId={1} resource="teachers" />)
    choose(container)
    const box = await screen.findByRole('region', { name: 'Check before importing' })
    expect(within(box).getByText(/2 questions before importing/)).toBeInTheDocument()
    const importButton = within(box).getByRole('button', { name: 'Answer 2 questions to import' })
    expect(importButton).toBeDisabled()

    fireEvent.click(within(box).getByLabelText('Yes, call them “Kavita Khana”'))
    expect(within(box).getByRole('button', { name: 'Answer the question to import' })).toBeDisabled()
    fireEvent.click(within(box).getByLabelText('No, keep “Comp Sci” as its own subject'))
    // The table shows the rows as they'll now be saved.
    expect(within(box).getAllByText('Kavita Khana')).toHaveLength(2)
    expect(within(box).getByText('Hindi, Comp Sci')).toBeInTheDocument()

    fireEvent.click(within(box).getByRole('button', { name: 'Import 3 teachers' }))
    await waitFor(() => expect(api.bulkImportCommit).toHaveBeenCalled())
    expect(api.bulkImportCommit.mock.calls[0][2]).toEqual([
      { name: 'Kavita Khana', qualified_subjects: 'Hindi' },
      { name: 'Kavita Khana', qualified_subjects: 'Hindi;Comp Sci' },
      { name: 'Anil', qualified_subjects: 'Maths' },
    ])
  })

  it('rooms still import in one step', async () => {
    api.bulkImport.mockResolvedValue({ created: 2, updated: 0, errors: [] })
    const { container } = render(<BulkImportPanel schoolId={1} resource="rooms" />)
    const input = container.querySelector('input[type="file"]')
    fireEvent.change(input, { target: { files: [new File(['x'], 'rooms.csv')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    await waitFor(() => expect(screen.getByText(/2 created/)).toBeInTheDocument())
    expect(api.bulkImportPreview).not.toHaveBeenCalled()
  })
})
