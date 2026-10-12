import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ api: { bulkImportTemplateUrl: () => '#', bulkImport: vi.fn() } }))
import SubjectsSection from './SubjectsSection'

const handlers = { create: vi.fn(), update: vi.fn(), delete: vi.fn() }
const props = { schoolId: 1, onSubjectsChanged: handlers, institutionType: 'school', readOnly: false }

describe('SubjectsSection saving row', () => {
  it('keeps the same row when a saving subject comes back with its real id', () => {
    const existing = { id: 1, name: 'Maths' }
    const pending = { id: 'temp-1', name: 'French', _pending: true }
    const { rerender } = render(<SubjectsSection {...props} subjects={[existing, pending]} />)
    const rowWhileSaving = screen.getByDisplayValue('French').closest('tr')
    expect(screen.getByText('Saving…')).toBeInTheDocument()

    rerender(<SubjectsSection {...props} subjects={[existing, { id: 2, name: 'French' }]} />)
    const rowAfterSave = screen.getByDisplayValue('French').closest('tr')

    expect(rowAfterSave).toBe(rowWhileSaving)
    expect(screen.queryByText('Saving…')).not.toBeInTheDocument()
    expect(screen.getAllByDisplayValue('French')).toHaveLength(1)
  })
})
