import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import StandardRules from './StandardRules'

describe('the tick-box rules on the Constraints page', () => {
  it('shows the defaults: caps off at 30 and 6, spreading on', () => {
    render(<StandardRules rules={null} onSave={vi.fn()} />)
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes.map((b) => b.checked)).toEqual([false, false, true])
    expect(screen.getByLabelText('Number of periods in a week').value).toBe('30')
    expect(screen.getByLabelText('Number of periods in a day').value).toBe('6')
  })

  it('ticking a box saves it with its number', async () => {
    const onSave = vi.fn(() => Promise.resolve())
    render(<StandardRules rules={null} onSave={onSave} />)
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ teacher_week_max: { on: true, value: 30 } }))
  })

  it('changing a number saves it, and a bad number is refused', async () => {
    const onSave = vi.fn(() => Promise.resolve())
    render(<StandardRules rules={{ teacher_day_max: { on: true, value: 6 } }} onSave={onSave} />)
    const day = screen.getByLabelText('Number of periods in a day')
    fireEvent.change(day, { target: { value: '7' } })
    fireEvent.blur(day)
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ teacher_day_max: { on: true, value: 7 } }))

    onSave.mockClear()
    fireEvent.change(day, { target: { value: '40' } })
    fireEvent.blur(day)
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toContain('1 to 16')
  })

  it('is read-only for viewers', () => {
    render(<StandardRules rules={null} onSave={vi.fn()} readOnly />)
    expect(screen.getAllByRole('checkbox').every((b) => b.disabled)).toBe(true)
  })
})
