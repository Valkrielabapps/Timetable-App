import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ConstraintsTab from './ConstraintsTab'
import { api } from '../api'

vi.mock('../api', () => ({
  api: { deleteConstraints: vi.fn(), deleteConstraint: vi.fn() },
}))
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [] }),
  useTimetable: () => ({ data: null }),
}))
vi.mock('./confirmDialog', () => ({ confirmDialog: vi.fn(async () => true) }))

const rule = (id, description) => ({
  id, school_id: 1, type: 'ir', parameters: {}, is_hard: true, weight: 1, description,
  enforced: true, conflicts: [], about: null,
})
const RULES = [rule(1, 'No PE in period 1'), rule(2, 'No Library on Saturday'), rule(3, 'Art after lunch')]

function setup() {
  const onReload = vi.fn().mockResolvedValue(undefined)
  render(<ConstraintsTab schoolId={1} classGroups={[]} constraints={RULES} onReload={onReload} />)
  return { onReload }
}

describe('Select mode on the Constraints tab', () => {
  beforeEach(() => {
    api.deleteConstraints.mockReset()
    api.deleteConstraints.mockResolvedValue({ deleted: 2 })
  })

  it('shows tick boxes only after Select is pressed', () => {
    setup()
    expect(screen.queryByRole('checkbox', { name: /select: no pe/i })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Select' }))
    expect(screen.getByRole('checkbox', { name: /select: no pe/i })).toBeInTheDocument()
  })

  it('deletes the ticked rules in one request', async () => {
    const { onReload } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Select' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /select: no pe/i }))
    fireEvent.click(screen.getByRole('checkbox', { name: /select: no library/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete 2' }))
    await waitFor(() => expect(api.deleteConstraints).toHaveBeenCalledWith(1, [1, 2]))
    expect(onReload).toHaveBeenCalled()
  })

  it('select all ticks every rule', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Select' }))
    fireEvent.click(screen.getByRole('button', { name: /select all \(3\)/i }))
    expect(screen.getByText('3 selected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete 3' }))
    await waitFor(() => expect(api.deleteConstraints).toHaveBeenCalledWith(1, [1, 2, 3]))
  })

  it('cancel leaves select mode without deleting', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Select' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /select: no pe/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('checkbox', { name: /select: no pe/i })).toBeNull()
    expect(api.deleteConstraints).not.toHaveBeenCalled()
  })
})

describe('batch lines that need adding on their own', () => {
  it('lists them with the reason and moves one into the single-rule box', async () => {
    api.parseConstraintsBatch = vi.fn().mockResolvedValue({
      created: [],
      unread: [{ text: 'No PE right after lunch', reason: 'Saturday has no lunch - weekdays only?' }],
    })
    const onReload = vi.fn().mockResolvedValue(undefined)
    render(<ConstraintsTab schoolId={1} classGroups={[]} constraints={[]} onReload={onReload} />)
    fireEvent.click(screen.getByText(/add them all together/i))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'No PE right after lunch' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add all' }))
    expect(await screen.findByText(/1 rule wasn't added/i)).toBeInTheDocument()
    expect(screen.getByText('Saturday has no lunch - weekdays only?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add on its own' }))
    expect(screen.getByDisplayValue('No PE right after lunch')).toBeInTheDocument()
  })
})
