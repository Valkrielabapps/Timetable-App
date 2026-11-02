import React from 'react'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'

const api = vi.hoisted(() => ({
  moveSlot: vi.fn(),
  moveTargets: vi.fn(),
  lockSlot: vi.fn(),
}))
vi.mock('../api', () => ({ api }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: undefined }) }))

const hooks = vi.hoisted(() => ({ timetable: null, optimisticSlotMove: vi.fn(() => vi.fn()) }))
vi.mock('../hooks/useSchoolData', () => ({
  useSetupCheck: () => ({ data: null, isLoading: false }),
  useTimetables: () => ({ data: [{ id: 1, status: 'draft' }] }),
  useTimetable: () => ({ data: hooks.timetable }),
  useGenerateTimetable: () => ({ generate: vi.fn(), isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useOptimisticSlotMove: () => hooks.optimisticSlotMove,
  useFrozenStatus: () => ({ data: [] }),
  useSetFrozen: () => ({ setFrozen: vi.fn(), isSaving: false }),
  useSubjectFreezes: () => ({ data: [] }),
  useSubjectFreezeActions: () => ({ freeze: vi.fn(), unfreeze: vi.fn(), isSaving: false }),
  useElectiveBlocks: () => ({ data: [] }),
}))

/**
 * While a lesson is dragged, every other period of its section is coloured:
 * green it can go, amber it can but a rule breaks, red it can't - and the red
 * cell under the pointer says why. A drop on red never reaches the server.
 */

const PERIODS = [1, 2, 3, 4].map((id) => ({ id, day_of_week: 0, order: id - 1, label: null, is_break: false }))
const CG = { id: 100, grade: 'Grade 11', name: 'A' }
const entry = (id, periodId, subject, teacher) => ({
  id, class_group_id: 100, class_group_name: 'A', subject_id: id, subject_name: subject,
  teacher_id: id, teacher_name: teacher, period_id: periodId, day_of_week: 0, order: periodId - 1,
  room_id: null, room_name: null, locked: false, lab_batch: null, elective_block_id: null,
})
const TIMETABLE = { id: 1, status: 'draft', violations: [], entries: [entry(1, 1, 'English', 'Verma')] }

const TARGETS = {
  from_period_id: 1,
  targets: [
    { period_id: 2, status: 'ok', reason: null },
    { period_id: 3, status: 'warn', reason: 'Breaks “No English in period 3”' },
    { period_id: 4, status: 'blocked', reason: 'Verma teaches Grade 11 B then' },
  ],
}

const cellAt = (order) => screen.getByText('Grade 11 · A').closest('section').querySelectorAll('tbody tr')[order].querySelectorAll('td')[1]

beforeEach(() => {
  api.moveSlot.mockReset()
  api.moveTargets.mockReset().mockResolvedValue(TARGETS)
  hooks.timetable = TIMETABLE
  render(<TimetableTab schoolId={1} classGroup={CG} classGroups={[CG]} teachers={[]} periods={PERIODS} constraints={[]} />)
})

async function pickUp() {
  fireEvent.dragStart(within(cellAt(0)).getByText('English').closest('[draggable]'))
  await waitFor(() => expect(cellAt(3)).toHaveAttribute('data-drop', 'blocked'))
}

describe('dragging a lesson', () => {
  it('asks where it can go as soon as it is picked up, and colours every cell', async () => {
    await pickUp()
    expect(api.moveTargets).toHaveBeenCalledWith(1, 100, 1)
    expect(cellAt(1)).toHaveAttribute('data-drop', 'ok')
    expect(cellAt(2)).toHaveAttribute('data-drop', 'warn')
    expect(cellAt(3).className).toMatch(/bg-red-100/)
    expect(screen.getByText('Allowed, breaks a rule')).toBeInTheDocument()
  })

  it('says why a red cell is blocked when dragged over it', async () => {
    await pickUp()
    fireEvent.dragEnter(cellAt(3))
    expect(within(cellAt(3)).getByRole('status')).toHaveTextContent('Verma teaches Grade 11 B then')
  })

  it('never sends a move it already knows will be refused', async () => {
    await pickUp()
    fireEvent.drop(cellAt(3))
    expect(api.moveSlot).not.toHaveBeenCalled()
    expect(await screen.findByText(/Can't move it there: Verma teaches Grade 11 B then/)).toBeInTheDocument()
  })

  it('moves onto amber and green as before', async () => {
    api.moveSlot.mockResolvedValue({ entries: [], violations: [] })
    await pickUp()
    await act(async () => { fireEvent.drop(cellAt(2)) })
    expect(api.moveSlot).toHaveBeenCalledWith(1, 100, 1, 3)
  })

  it('clears the colours when the drag ends', async () => {
    await pickUp()
    fireEvent.dragEnd(within(cellAt(0)).getByText('English').closest('[draggable]'))
    await waitFor(() => expect(cellAt(3)).not.toHaveAttribute('data-drop'))
  })
})
