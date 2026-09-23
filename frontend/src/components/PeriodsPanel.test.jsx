import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PeriodsPanel from './PeriodsPanel'

const SAMPLE_PERIODS = [
  { id: 1, day_of_week: 0, order: 1, label: '9:00-9:45' },
  { id: 2, day_of_week: 0, order: 2, label: null },
]

describe('PeriodsPanel', () => {
  it('renders every period passed in', () => {
    render(<PeriodsPanel schoolId={1} periods={SAMPLE_PERIODS} onCreate={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText(/Monday · #1 · 9:00-9:45/)).toBeInTheDocument()
    expect(screen.getByText(/Monday · #2/)).toBeInTheDocument()
  })

  it('shows an empty-state message when there are no periods yet', () => {
    render(<PeriodsPanel schoolId={1} periods={[]} onCreate={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('No periods yet.')).toBeInTheDocument()
  })

  it('calls onCreate with the entered values when the add form is submitted', () => {
    const onCreate = vi.fn().mockResolvedValue(undefined)
    render(<PeriodsPanel schoolId={7} periods={[]} onCreate={onCreate} onDelete={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText('Order (1, 2, 3…)'), { target: { value: '3' } })
    fireEvent.change(screen.getByPlaceholderText('Label (e.g. 9:00-9:45)'), { target: { value: '11:00-11:45' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    expect(onCreate).toHaveBeenCalledWith({
      school_id: 7,
      day_of_week: 0,
      order: 3,
      label: '11:00-11:45',
      is_break: false,
    })
  })

  it('calls onDelete with the period id when Remove is clicked', () => {
    const onDelete = vi.fn().mockResolvedValue(undefined)
    render(<PeriodsPanel schoolId={1} periods={SAMPLE_PERIODS} onCreate={vi.fn()} onDelete={onDelete} />)

    fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0])
    expect(onDelete).toHaveBeenCalledWith(1)
  })

  // This is the exact bug fixed earlier this session (see
  // docs/ARCHITECTURE.md's "Multiple admins per school..." section):
  // DataEntryTab.jsx's SetupSection received `readOnly` correctly but
  // never forwarded it into PeriodsPanel/RoomsPanel, so a viewer saw full
  // edit controls and only found out they couldn't act on them from a 403
  // after submitting. This test exists specifically so that regression
  // can't silently come back.
  describe('when readOnly', () => {
    it('hides the add form and every Remove button', () => {
      render(<PeriodsPanel schoolId={1} periods={SAMPLE_PERIODS} onCreate={vi.fn()} onDelete={vi.fn()} readOnly />)

      expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
      // The read-only list itself should still render normally.
      expect(screen.getByText(/Monday · #1/)).toBeInTheDocument()
    })
  })
})

describe('PeriodsPanel breaks', () => {
  const WITH_BREAK = [
    { id: 1, day_of_week: 0, order: 1, label: '9:00-9:45', is_break: false },
    { id: 2, day_of_week: 0, order: 2, label: 'Lunch', is_break: true },
  ]

  it('marks a break visibly, so it is obvious nothing is taught then', () => {
    render(
      <PeriodsPanel schoolId={1} periods={WITH_BREAK} onCreate={vi.fn()} onDelete={vi.fn()} onUpdate={vi.fn()} />,
    )
    expect(screen.getByText('Break', { selector: 'span' })).toBeInTheDocument()
  })

  it('creates a period as a break when the box is ticked', async () => {
    const onCreate = vi.fn().mockResolvedValue({})
    render(<PeriodsPanel schoolId={7} periods={[]} onCreate={onCreate} onDelete={vi.fn()} onUpdate={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText(/Order/), { target: { value: '4' } })
    fireEvent.click(screen.getByLabelText('Break'))
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ is_break: true, order: 4 }))
  })

  it('toggles an existing period between teaching and break', () => {
    const onUpdate = vi.fn().mockResolvedValue({})
    render(
      <PeriodsPanel schoolId={1} periods={WITH_BREAK} onCreate={vi.fn()} onDelete={vi.fn()} onUpdate={onUpdate} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Mark as break' }))
    expect(onUpdate).toHaveBeenCalledWith(1, { is_break: true })

    fireEvent.click(screen.getByRole('button', { name: 'Mark as teaching' }))
    expect(onUpdate).toHaveBeenCalledWith(2, { is_break: false })
  })

  it('hides the break controls from viewers', () => {
    render(
      <PeriodsPanel schoolId={1} periods={WITH_BREAK} onCreate={vi.fn()} onDelete={vi.fn()} onUpdate={vi.fn()} readOnly />,
    )
    expect(screen.queryByRole('button', { name: /Mark as/ })).not.toBeInTheDocument()
    // the badge still shows - a viewer should see which slots are breaks
    expect(screen.getByText('Break', { selector: 'span' })).toBeInTheDocument()
  })
})
