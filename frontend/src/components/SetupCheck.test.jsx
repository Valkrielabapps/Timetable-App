import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'
import SetupCheckPanel from './SetupCheckPanel'

vi.mock('../api', () => ({ api: {} }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: undefined }) }))
const generate = vi.fn(() => Promise.resolve())
const check = vi.hoisted(() => ({ current: null }))
vi.mock('../hooks/useSchoolData', () => ({
  usePlanChanges: () => ({ data: null }),
  useRefreshAll: () => () => {},
  useSetupCheck: () => ({ data: check.current, isLoading: false }),
  useTimetables: () => ({ data: [] }),
  useTimetable: () => ({ data: null }),
  useGenerateTimetable: () => ({ generate, isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useRooms: () => ({ data: [] }),
  useVersionActions: () => ({ open: vi.fn() }),
  useElectiveBlocks: () => ({ data: [] }),
  useFrozenStatus: () => ({ data: [] }),
  useSetFrozen: () => ({ setFrozen: vi.fn(), isSaving: false }),
  useSubjectFreezes: () => ({ data: [] }),
  useSubjectFreezeActions: () => ({ freeze: vi.fn(), unfreeze: vi.fn(), isSaving: false }),
}))

vi.mock('../hooks/useTimetableEdits', () => ({
  useTimetableEdits: () => ({ undoCount: 0, revision: 0 }),
  useLessons: () => ({ data: [] }),
  useForecast: () => null,
  useStartBlank: () => vi.fn(),
}))

const section = { id: 1, grade: 'Grade 9', name: 'A' }
const overfull = {
  severity: 'error', kind: 'section_overfull',
  message: 'Grade 9 A needs 9 periods a week but its week has only 8.',
  fix: { type: 'section', id: 1, label: 'Open Grade 9 A' },
}
const noRoom = {
  severity: 'warning', kind: 'no_room_type',
  message: 'Chem Lab needs a “chem” room, but the school has none.',
  fix: { type: 'rooms', id: null, label: 'Open rooms' },
}

function renderTab(onFix = vi.fn()) {
  render(<TimetableTab schoolId={1} classGroup={section} classGroups={[section]} teachers={[]} periods={[]}
    constraints={[]} onFix={onFix} />)
  return onFix
}

beforeEach(() => {
  generate.mockClear()
  check.current = null
})

describe('the setup check above Generate', () => {
  it('says so when nothing was found', () => {
    check.current = { ok: true, errors: [], warnings: [] }
    renderTab()
    expect(screen.getByText(/nothing found that would stop a timetable/)).toBeInTheDocument()
  })

  it('lists problems, and Fix opens the thing each is about', () => {
    check.current = { ok: false, errors: [overfull], warnings: [noRoom] }
    const onFix = renderTab()
    const panel = screen.getByRole('region', { name: 'Setup check' })
    expect(panel).toHaveTextContent('1 problem will stop the timetable from generating')
    expect(panel).toHaveTextContent('and 1 to look at')
    expect(panel).toHaveTextContent('Grade 9 A needs 9 periods')
    fireEvent.click(within(panel).getAllByRole('button', { name: 'Fix' })[0])
    expect(onFix).toHaveBeenCalledWith(overfull.fix)
  })

  it('asks before generating when a problem is certain to stop it', async () => {
    check.current = { ok: false, errors: [overfull], warnings: [] }
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Generate timetable' }))
    expect(generate).not.toHaveBeenCalled()
    const ask = screen.getByRole('alertdialog', { name: 'Setup problems' })
    expect(ask).toHaveTextContent('will stop the timetable')
    fireEvent.click(within(ask).getByRole('button', { name: 'Generate anyway' }))
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1))
  })

  it('generates straight away when there are only warnings', async () => {
    check.current = { ok: true, errors: [], warnings: [noRoom] }
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Generate timetable' }))
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alertdialog', { name: 'Setup problems' })).not.toBeInTheDocument()
  })
})

describe('a long list', () => {
  it('shows five, then all on request', () => {
    const errors = Array.from({ length: 7 }, (_, i) => ({ ...overfull, message: `Problem ${i + 1}` }))
    render(<SetupCheckPanel check={{ errors, warnings: [] }} onFix={vi.fn()} />)
    expect(screen.queryByText('Problem 6')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 7' }))
    expect(screen.getByText('Problem 7')).toBeInTheDocument()
  })
})
