import React from 'react'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'

const api = vi.hoisted(() => ({ acceptCompromise: vi.fn() }))
vi.mock('../api', () => ({ api }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: undefined }) }))
const hooks = vi.hoisted(() => ({ timetable: null }))
vi.mock('../hooks/useSchoolData', () => ({
  useSetupCheck: () => ({ data: null, isLoading: false }),
  useTimetables: () => ({ data: [{ id: 7, status: 'draft' }] }),
  useTimetable: () => ({ data: hooks.timetable }),
  useGenerateTimetable: () => ({ generate: vi.fn(), isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useOptimisticSlotMove: () => vi.fn(),
  useFrozenStatus: () => ({ data: [] }),
  useSetFrozen: () => ({ setFrozen: vi.fn(), isSaving: false }),
  useSubjectFreezes: () => ({ data: [] }),
  useSubjectFreezeActions: () => ({ freeze: vi.fn(), unfreeze: vi.fn(), isSaving: false }),
  useElectiveBlocks: () => ({ data: [] }),
}))

const CG = { id: 1, grade: 'Grade 9', name: 'A' }
const base = { id: 7, status: 'draft', version_number: 4, entries: [], violations: [] }
const compromise = {
  rules: ['No Maths in the last period'],
  reason: ['The rule “No Maths in the last period” makes the timetable impossible.'],
  accepted: false,
}

function renderTab(props = {}) {
  render(<TimetableTab schoolId={1} classGroup={CG} classGroups={[CG]} teachers={[]} periods={[]} constraints={[]} {...props} />)
}

beforeEach(() => {
  api.acceptCompromise.mockReset().mockResolvedValue({})
})

describe('a timetable made with compromises', () => {
  it('says which rules were bent, and why when asked', () => {
    hooks.timetable = { ...base, compromise }
    renderTab()
    const notice = screen.getByRole('region', { name: 'Made with compromises' })
    expect(notice).toHaveTextContent('bends one of them as little as possible')
    expect(notice).toHaveTextContent('“No Maths in the last period”')
    expect(notice).toHaveTextContent('no teacher or room is double-booked')
    fireEvent.click(within(notice).getByRole('button', { name: /Why couldn/ }))
    expect(notice).toHaveTextContent('makes the timetable impossible')
  })

  it('keeps it, and the notice goes', async () => {
    hooks.timetable = { ...base, compromise }
    renderTab()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Keep this timetable' }))
    })
    expect(api.acceptCompromise).toHaveBeenCalledWith(7)
    expect(screen.queryByRole('region', { name: 'Made with compromises' })).not.toBeInTheDocument()
  })

  it('goes to the rules to change them', () => {
    hooks.timetable = { ...base, compromise }
    const onOpenConstraints = vi.fn()
    renderTab({ onOpenConstraints })
    fireEvent.click(screen.getByRole('button', { name: 'Change the rules' }))
    expect(onOpenConstraints).toHaveBeenCalled()
  })

  it('shows nothing once kept, or for an ordinary timetable', () => {
    hooks.timetable = { ...base, compromise: { ...compromise, accepted: true } }
    renderTab()
    expect(screen.queryByRole('region', { name: 'Made with compromises' })).not.toBeInTheDocument()
  })
})
