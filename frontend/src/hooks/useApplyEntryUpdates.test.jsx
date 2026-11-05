import React from 'react'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { keys } from '../queryClient'
import { useApplyEntryUpdates } from './useSchoolData'

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

describe('useApplyEntryUpdates', () => {
  it('adds new rows and drops removed ones', () => {
    const { result, read } = setup(() => useApplyEntryUpdates(3))
    const before = read().entries
    act(() => result.current({ entries: [{ id: 999, period_id: 1 }], removed_ids: [before[0].id] }))
    const ids = read().entries.map((e) => e.id)
    expect(ids).toContain(999)
    expect(ids).not.toContain(before[0].id)
    expect(ids).toHaveLength(before.length)
  })

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
