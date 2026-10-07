import React from 'react'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { keys } from '../queryClient'
import { useApplyEntryUpdates, useOptimisticSlotMove } from './useSchoolData'

vi.mock('../api', () => ({ api: {} }))

/**
 * Moving a slot in the cache before the server has agreed to it.
 *
 * Dragging used to wait for the round trip before the cell moved, so every
 * drag cost one API call of visible lag on an interaction that should feel
 * like picking a card up and putting it down.
 *
 * The rollback is the half that makes it honest. The move is a guess - the
 * server can still refuse it, usually because the target double-books a
 * teacher - and a cell that stays where it was dropped after a rejection is
 * worse than the lag ever was: the screen and the database disagree, and only
 * one of them is right.
 */

// Section 100: a lesson in period 10, a three-option block in period 11,
// nothing in period 12. Section 200 also uses period 10 - a slot is one
// section's period, and the other section's lesson must never come along.
const P10 = { id: 10, day_of_week: 0, order: 0 }
const P11 = { id: 11, day_of_week: 0, order: 1 }
const P12 = { id: 12, day_of_week: 1, order: 3 }

const TIMETABLE = {
  id: 3,
  status: 'draft',
  entries: [
    { id: 1, class_group_id: 100, period_id: 10, day_of_week: 0, order: 0 },
    { id: 2, class_group_id: 100, period_id: 11, day_of_week: 0, order: 1, elective_block_id: 5 },
    { id: 3, class_group_id: 100, period_id: 11, day_of_week: 0, order: 1, elective_block_id: 5 },
    { id: 4, class_group_id: 100, period_id: 11, day_of_week: 0, order: 1, elective_block_id: 5 },
    { id: 9, class_group_id: 200, period_id: 10, day_of_week: 0, order: 0 },
  ],
  violations: [],
}

function setup(hook) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(keys.timetable(3), TIMETABLE)
  const Wrapper = ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(hook, { wrapper: Wrapper })
  return { result, client, read: () => client.getQueryData(keys.timetable(3)) }
}

const entry = (data, id) => data.entries.find((e) => e.id === id)

describe('useOptimisticSlotMove', () => {
  it('moves a lesson into a free cell straight away, without waiting for anything', () => {
    const { result, read } = setup(() => useOptimisticSlotMove(3))
    act(() => {
      result.current(100, P10, P12)
    })
    expect(entry(read(), 1)).toMatchObject({ period_id: 12, day_of_week: 1, order: 3 })
  })

  it('moves every option of a block together', () => {
    // Moving one option alone would leave the block's subjects in different
    // periods, which is no longer a block.
    const { result, read } = setup(() => useOptimisticSlotMove(3))
    act(() => {
      result.current(100, P11, P12)
    })
    for (const id of [2, 3, 4]) {
      expect(entry(read(), id)).toMatchObject({ period_id: 12, day_of_week: 1, order: 3 })
    }
  })

  it('sends whatever was in the target back the other way', () => {
    // A block dropped on a lesson trades places with it, all in one write, so
    // the two are never shown in the same cell.
    const { result, read } = setup(() => useOptimisticSlotMove(3))
    act(() => {
      result.current(100, P11, P10)
    })
    for (const id of [2, 3, 4]) expect(entry(read(), id)).toMatchObject({ period_id: 10, order: 0 })
    expect(entry(read(), 1)).toMatchObject({ period_id: 11, order: 1 })
  })

  it("leaves other sections' lessons in the same period alone", () => {
    const { result, read } = setup(() => useOptimisticSlotMove(3))
    act(() => {
      result.current(100, P10, P12)
    })
    expect(entry(read(), 9)).toMatchObject({ period_id: 10, order: 0 })
  })

  it('puts every cell back when the server refuses', () => {
    // A cell that stays where it was dropped after a rejection is worse than
    // the lag: the screen and the database disagree.
    const { result, read } = setup(() => useOptimisticSlotMove(3))
    let rollback
    act(() => {
      rollback = result.current(100, P11, P10)
    })
    // Asserted before rolling back, because a move that never happened rolls
    // back to the same place and this test would pass against a no-op.
    expect(entry(read(), 2)).toMatchObject({ period_id: 10 })
    act(() => rollback())
    expect(read()).toEqual(TIMETABLE)
  })

  it('does not guess at which rules the move breaks', () => {
    // Working that out in the browser means a second implementation of the
    // rule engine, and two of those drifting apart is worse than a banner that
    // settles a moment late. The server sends the real answer back.
    const { result, read } = setup(() => useOptimisticSlotMove(3))
    act(() => {
      result.current(100, P10, P12)
    })
    expect(read().violations).toEqual([])
  })
})

describe('useApplyEntryUpdates', () => {
  it('patches the violations the server sent back with the rows', () => {
    // Without this the warning band goes stale the moment a slot moves, which
    // is exactly when it has something to say.
    const { result, read } = setup(() => useApplyEntryUpdates(3))
    const violation = {
      constraint_id: 7, description: 'No class has PE in period 1.',
      strength: 'required', entry_ids: [1], detail: '1 period here, but the rule says exactly 0',
    }
    act(() => {
      result.current({ entries: [{ id: 1, period_id: 12 }], violations: [violation] })
    })
    expect(read().violations).toEqual([violation])
  })

  it('clears the band when an edit fixes the last violation', () => {
    const { result, client, read } = setup(() => useApplyEntryUpdates(3))
    client.setQueryData(keys.timetable(3), {
      ...TIMETABLE,
      violations: [{ constraint_id: 7, description: 'x', strength: 'required',
                     entry_ids: [1], detail: 'y' }],
    })
    act(() => {
      result.current({ entries: [{ id: 1, period_id: 10 }], violations: [] })
    })
    expect(read().violations).toEqual([])
  })

  it('keeps the existing violations when a response carries none', () => {
    // An older response, or one from a path that does not recompute them.
    // Blanking the band on a response that simply said nothing about it would
    // hide a real warning.
    const { result, client, read } = setup(() => useApplyEntryUpdates(3))
    const existing = [{ constraint_id: 7, description: 'x', strength: 'required',
                        entry_ids: [1], detail: 'y' }]
    client.setQueryData(keys.timetable(3), { ...TIMETABLE, violations: existing })
    act(() => {
      result.current({ entries: [{ id: 1, period_id: 10 }] })
    })
    expect(read().violations).toEqual(existing)
  })
})
