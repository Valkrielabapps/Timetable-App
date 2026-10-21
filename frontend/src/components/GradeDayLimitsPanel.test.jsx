import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import GradeDayLimitsPanel from './GradeDayLimitsPanel'

const LESSONS = { 0: 8, 1: 8, 2: 8, 3: 8, 4: 8, 5: 4 }

describe('shorter days for some grades', () => {
  it('saves grades, periods a day and a day off', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(<GradeDayLimitsPanel grades={['Grade 1', 'Grade 2', 'Grade 3']} limits={null} lessonsByDay={LESSONS} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Add a shorter day' }))
    fireEvent.click(screen.getByRole('button', { name: 'Grade 1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Grade 2' }))
    fireEvent.change(screen.getByLabelText('Periods a day'), { target: { value: '6' } })
    fireEvent.change(screen.getByLabelText('Periods on Saturday'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith([{ grades: ['Grade 1', 'Grade 2'], periods_per_day: 6, by_day: { 5: 0 } }]),
    )
    expect(await screen.findByText(/generate again to apply/i)).toBeInTheDocument()
  })

  it('shows a saved rule, and a grade can only be in one rule', () => {
    render(
      <GradeDayLimitsPanel
        grades={['Grade 1', 'Grade 2']}
        limits={[{ grades: ['Grade 1'], periods_per_day: 6, by_day: {} }]}
        lessonsByDay={LESSONS}
        onSave={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Grade 1' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Periods a day')).toHaveValue('6')
    fireEvent.click(screen.getByRole('button', { name: '+ Add a shorter day' }))
    const grade1Buttons = screen.getAllByRole('button', { name: 'Grade 1' })
    expect(grade1Buttons[1]).toBeDisabled()
  })
})
