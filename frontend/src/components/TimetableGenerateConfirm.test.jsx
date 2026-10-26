import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'

vi.mock('../api', () => ({ api: {} }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: undefined }) }))
const generate = vi.fn(() => Promise.resolve())
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 1, status: 'draft', version_number: 3, is_current: true }] }),
  useTimetable: (id) => ({ data: id ? { id: 1, status: 'draft', version_number: 3, entries: [], violations: [] } : null }),
  useGenerateTimetable: () => ({ generate, isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useOptimisticSlotMove: () => vi.fn(),
  useElectiveBlocks: () => ({ data: [] }),
  useFrozenStatus: () => ({ data: [
    { class_group_id: 1, frozen: true, frozen_from: 'Version 3' },
    { class_group_id: 2, frozen: true, frozen_from: 'Version 3' },
  ] }),
  useSetFrozen: () => ({ setFrozen: vi.fn(), isSaving: false }),
}))

const sections = [
  { id: 1, grade: 'Grade 1', name: 'A' }, { id: 2, grade: 'Grade 1', name: 'B' },
  { id: 3, grade: 'Grade 6', name: 'A' },
]

describe('generating with frozen sections', () => {
  it('says what it keeps, from which version, and what it builds - then generates', async () => {
    render(<TimetableTab schoolId={1} classGroup={sections[0]} classGroups={sections} teachers={[]} periods={[]} constraints={[]} />)
    expect(screen.getByText(/Showing/)).toHaveTextContent('Version 3')
    fireEvent.click(screen.getByRole('button', { name: 'Generate Timetable' }))
    expect(generate).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('Grade 1 (2 sections, frozen from Version 3)')
    expect(dialog).toHaveTextContent('Grade 6 (1 section)')
    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1))
  })
})
