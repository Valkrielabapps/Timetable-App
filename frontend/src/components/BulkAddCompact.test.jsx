import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import BulkAddClassGroups from './BulkAddClassGroups'

describe('adding a range of grades from the sidebar', () => {
  it('fits the narrow sidebar and still creates the sections', async () => {
    const onAdd = vi.fn(() => Promise.resolve())
    render(<BulkAddClassGroups compact onAddClassGroups={onAdd} institutionType="school" />)
    const from = screen.getByLabelText('From grade')
    expect(from.className).toContain('w-full')
    fireEvent.change(from, { target: { value: '7' } }) // Grade 6
    fireEvent.change(screen.getByLabelText('To grade'), { target: { value: '9' } }) // Grade 8
    const create = screen.getByRole('button', { name: 'Create 9 sections' })
    expect(create.className).toContain('w-full')
    fireEvent.click(create)
    await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1))
    expect(onAdd.mock.calls[0][0]).toHaveLength(9)
  })
})
