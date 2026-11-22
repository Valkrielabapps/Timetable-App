import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ clearSchoolData: vi.fn() }))
vi.mock('../api', () => ({ api }))
import ClearDataSection from './ClearDataSection'

const school = { id: 3, name: 'Keren Public School' }

describe('Clear all data', () => {
  it('asks for the school name before deleting anything', async () => {
    api.clearSchoolData.mockResolvedValue({ deleted: {} })
    const onCleared = vi.fn()
    render(<ClearDataSection school={school} isAdmin onCleared={onCleared} />)
    fireEvent.click(screen.getByRole('button', { name: 'Clear all data…' }))
    const go = screen.getByRole('button', { name: 'Delete all of this school’s data' })
    expect(go).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/type the school’s name/), { target: { value: 'Keren' } })
    expect(go).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/type the school’s name/), { target: { value: 'keren public school' } })
    fireEvent.click(go)
    await waitFor(() => expect(api.clearSchoolData).toHaveBeenCalledWith(3, 'keren public school'))
    expect(onCleared).toHaveBeenCalled()
  })

  it('is not offered to someone who is not an admin', () => {
    render(<ClearDataSection school={school} isAdmin={false} />)
    expect(screen.queryByRole('button', { name: 'Clear all data…' })).not.toBeInTheDocument()
  })
})
