import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import FixedPeriodsPanel from './FixedPeriodsPanel'

const SUBJECTS = [{ id: 1, name: 'C.T' }, { id: 2, name: 'Maths' }]
const GRADES = ['Grade 1', 'Grade 2', 'Grade 6']
const WEEK = { 0: 9, 1: 9, 2: 9, 3: 9, 4: 9 }

describe('fixed periods for some grades', () => {
  it('adds the class teacher period in period 8 for Grades 1 and 2, every day', async () => {
    const onSave = vi.fn().mockResolvedValue()
    render(<FixedPeriodsPanel grades={GRADES} subjects={SUBJECTS} rules={null} lessonsByDay={WEEK} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Add a fixed period' }))
    expect(screen.getByText('Choose a subject and at least one grade.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: '1' } })
    expect(screen.getByLabelText('Period')).toHaveValue('8')
    fireEvent.click(screen.getByRole('button', { name: 'Grade 1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Grade 2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSave).toHaveBeenCalledWith([{ subject_id: 1, grades: ['Grade 1', 'Grade 2'], period: 8, days: null }]))
    expect(await screen.findByText(/Saved. Generate again/)).toBeInTheDocument()
  })

  it('can leave out a day', async () => {
    const onSave = vi.fn().mockResolvedValue()
    render(<FixedPeriodsPanel grades={GRADES} subjects={SUBJECTS} lessonsByDay={WEEK} onSave={onSave}
      rules={[{ subject_id: 1, grades: ['Grade 1'], period: 8, days: null }]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Fri' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSave).toHaveBeenCalledWith([{ subject_id: 1, grades: ['Grade 1'], period: 8, days: [0, 1, 2, 3] }]))
  })
})
