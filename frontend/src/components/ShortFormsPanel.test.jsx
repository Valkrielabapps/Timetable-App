import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ShortFormsPanel from './ShortFormsPanel'

const api = vi.hoisted(() => ({ shortForms: vi.fn(), addShortForm: vi.fn(), deleteShortForm: vi.fn() }))
vi.mock('../api', () => ({ api }))

const BEAUL = { id: 1, kind: 'teacher', text: 'BEAUL', meaning: 'Beula Rao', source: 'timetable' }
const WRK = { id: 2, kind: 'subject', text: 'WRKSHP', meaning: 'Workshop', source: 'subjects' }

describe('ShortFormsPanel', () => {
  beforeEach(() => vi.resetAllMocks())

  it('lists only its kind and forgets one', async () => {
    api.shortForms.mockResolvedValue({ items: [BEAUL, WRK] })
    api.deleteShortForm.mockResolvedValue({ items: [WRK] })
    render(<ShortFormsPanel schoolId={3} kind="teacher" />)
    expect(await screen.findByText('BEAUL')).toBeInTheDocument()
    expect(screen.queryByText('WRKSHP')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Forget BEAUL' }))
    await waitFor(() => expect(api.deleteShortForm).toHaveBeenCalledWith(3, 1))
    expect(await screen.findByText('None yet.')).toBeInTheDocument()
  })

  it('adds one by hand', async () => {
    api.shortForms.mockResolvedValue({ items: [] })
    api.addShortForm.mockResolvedValue({ items: [WRK] })
    render(<ShortFormsPanel schoolId={3} kind="subject" />)
    fireEvent.change(await screen.findByLabelText('Short form'), { target: { value: 'WRKSHP' } })
    fireEvent.change(screen.getByLabelText('Full subject name'), { target: { value: 'Workshop' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(api.addShortForm).toHaveBeenCalledWith(3, { kind: 'subject', text: 'WRKSHP', meaning: 'Workshop' }))
    expect(await screen.findByText('Workshop')).toBeInTheDocument()
  })
})
