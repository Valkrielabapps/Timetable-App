import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ api: { downloadTimetableExport: vi.fn() } }))
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 1, status: 'draft' }], isLoading: false }),
  useTimetable: () => ({
    isLoading: false,
    data: {
      entries: [
        { id: 1, day_of_week: 0, period_id: 10, class_group_id: 5, class_group_name: '8-A', subject_id: 1, subject_name: 'Maths', teacher_id: 7, teacher_name: 'Asha', room_id: null, room_name: null },
      ],
    },
  }),
}))
import CalendarTab from './CalendarTab'

const periods = [{ id: 10, day_of_week: 0, order: 1, label: 'P1', is_break: false }]
const props = {
  schoolId: 1,
  periods,
  teachers: [{ id: 7, name: 'Asha' }],
  classGroups: [{ id: 5, grade: '8', name: 'A' }],
}

describe('CalendarTab', () => {
  it("shows a Monday's lessons against the teacher", () => {
    render(<CalendarTab {...props} initialDate={new Date(2026, 9, 5)} />) // Mon 5 Oct 2026
    expect(screen.getByText('Maths')).toBeInTheDocument()
    expect(screen.getByText('Asha')).toBeInTheDocument()
  })

  it('shows the empty state on a day with no periods', () => {
    render(<CalendarTab {...props} initialDate={new Date(2026, 9, 4)} />) // Sunday
    expect(screen.getByText('No Schedule Available')).toBeInTheDocument()
  })

  it('opens a day from the month view', () => {
    render(<CalendarTab {...props} initialDate={new Date(2026, 9, 4)} />)
    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    fireEvent.click(document.querySelector('[data-date="2026-10-05"]'))
    expect(screen.getByText('Maths')).toBeInTheDocument()
  })
})
