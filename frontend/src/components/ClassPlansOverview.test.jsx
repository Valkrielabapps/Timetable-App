import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ api: {} }))
vi.mock('../hooks/useSchoolData', () => ({
  useElectiveBlockMutations: () => ({}), useElectiveBlocks: () => ({ data: [] }),
  useRoomMutations: () => ({}), useRooms: () => ({ data: [] }),
}))
import { ClassPlansOverview } from './DataEntryTab'

const PERIODS = Array.from({ length: 10 }, (_, i) => ({ id: i + 1, kind: 'lesson' }))
const SECTIONS = [
  { id: 1, grade: 'Grade 1', name: 'A' }, { id: 2, grade: 'Grade 1', name: 'B' }, { id: 3, grade: 'Grade 2', name: 'A' },
]
const REQS = [
  { class_group_id: 1, periods_per_week: 6 }, { class_group_id: 1, periods_per_week: 4 },
  { class_group_id: 2, periods_per_week: 7 },
]

describe('class plans overview', () => {
  it('shows every section against the week and opens one', () => {
    const onPick = vi.fn()
    render(<ClassPlansOverview classGroups={SECTIONS} allRequirements={REQS} periods={PERIODS} activeSectionId={2} onPick={onPick} />)
    expect(screen.getByText('1 of 3 sections fill the week\'s 10 lessons')).toBeInTheDocument()
    expect(screen.getByTitle('10 of 10 periods planned')).toHaveClass('bg-emerald-50')
    expect(screen.getByTitle('7 of 10 periods planned')).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByTitle('0 of 10 periods planned'))
    expect(onPick).toHaveBeenCalledWith(3)
  })
})
