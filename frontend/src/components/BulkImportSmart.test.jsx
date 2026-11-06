import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import BulkImportPanel from './BulkImportPanel'

const api = vi.hoisted(() => ({ bulkImport: vi.fn(), bulkImportTemplateUrl: () => '#' }))
vi.mock('../api', () => ({ api }))

describe('importing a school’s own staff list', () => {
  it('says any layout works, and afterwards how the sheet was read', async () => {
    api.bulkImport.mockResolvedValue({
      created: 2, updated: 0, errors: [], sheet: 'Staff',
      read_as: ['“Name of Teacher” as teacher’s full name', '“Subject 1” as subjects they teach'],
      new_subjects: ['Maths', 'Physics'],
    })
    const { container } = render(<BulkImportPanel schoolId={1} resource="teachers" />)
    expect(screen.getByText(/in any layout/)).toBeInTheDocument()
    expect(screen.queryByText(/^Columns:/)).not.toBeInTheDocument()
    const input = container.querySelector('input[type="file"]')
    fireEvent.change(input, { target: { files: [new File(['x'], 'staff.xlsx')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    await waitFor(() => expect(screen.getByText(/2 created/)).toBeInTheDocument())
    expect(screen.getByText(/Read the sheet “Staff”/)).toHaveTextContent('“Name of Teacher” as teacher’s full name')
    expect(screen.getByText(/Added 2 new subjects: Maths, Physics/)).toBeInTheDocument()
  })
})
