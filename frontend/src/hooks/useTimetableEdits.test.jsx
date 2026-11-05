import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { useTimetableEdits } from './useTimetableEdits'

vi.mock('../api', () => ({
  api: {
    moveSlot: vi.fn(), placeLesson: vi.fn(), removeSlot: vi.fn(), restoreSlot: vi.fn(), lockSlot: vi.fn(),
    forecast: vi.fn(), listLessons: vi.fn(), startBlankTimetable: vi.fn(),
  },
}))

/**
 * An edit shows at once, then the server is told. The things that must hold:
 * the screen never waits, requests go in order, a refusal puts back only its
 * own edit, and the server's answer replaces the guess.
 */

const P1 = { id: 11, day_of_week: 0, order: 0 }
const P2 = { id: 12, day_of_week: 0, order: 1 }
const periods = new Map([[11, P1], [12, P2]])
const row = (id, section, period, more = {}) => ({
  id, class_group_id: section, period_id: period.id, day_of_week: period.day_of_week, order: period.order,
  subject_id: 5, subject_name: 'Maths', teacher_id: 7, locked: false, ...more,
})
const lesson = { key: 'r1', kind: 'subject', class_group_id: 1, section_ids: [1], subject_id: 9, label: 'Physics' }

function setup(entries = []) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['timetable', 1], { id: 1, entries, violations: [] })
  const onRefused = vi.fn()
  const onMoveRefused = vi.fn()
  const wrapper = ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useTimetableEdits(1, periods, { onRefused, onMoveRefused }), { wrapper })
  return { result, onRefused, onMoveRefused, read: () => client.getQueryData(['timetable', 1]) }
}

const deferred = () => {
  let resolve, reject
  const promise = new Promise((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}

beforeEach(() => vi.clearAllMocks())

describe('placing a lesson', () => {
  it('shows before the server answers, then takes the real row', async () => {
    const answer = deferred()
    api.placeLesson.mockReturnValue(answer.promise)
    const { result, read } = setup()
    act(() => { result.current.place(lesson, 7, P1, [7], () => 'Mrs Susan') })
    expect(read().entries).toHaveLength(1)
    expect(read().entries[0]).toMatchObject({ subject_name: 'Physics', teacher_name: 'Mrs Susan', period_id: 11 })
    expect(read().entries[0].id).toBeLessThan(0)
    await act(async () => {
      answer.resolve({ entries: [row(99, 1, P1, { subject_name: 'Physics' })], violations: [{ description: 'A rule' }] })
      await answer.promise
    })
    await waitFor(() => expect(read().entries.map((e) => e.id)).toEqual([99]))
    expect(read().violations).toEqual([{ description: 'A rule' }])
  })

  it('takes it back and says why when refused', async () => {
    api.placeLesson.mockRejectedValue(new Error('400 Nope'))
    const { result, read, onRefused } = setup()
    await act(async () => { await result.current.place(lesson, 7, P1, [7]) })
    expect(read().entries).toEqual([])
    expect(onRefused.mock.calls[0][0].message).toBe('400 Nope')
  })

  it('sends a block by its id', async () => {
    api.placeLesson.mockResolvedValue({ entries: [] })
    const block = {
      kind: 'block', block_id: 4, label: 'Block A', section_ids: [1],
      options: [{ option_id: 1, subject_id: 2, subject_name: 'Physics', section_ids: [1], teacher_ids: [7], preferred_teacher_id: null }],
    }
    const { result } = setup()
    await act(async () => { await result.current.place(block, 7, P1, [7]) })
    expect(api.placeLesson).toHaveBeenCalledWith(1, { block_id: 4, teacher_id: 7, period_id: 11 })
  })
})

describe('moving a lesson', () => {
  const slot = (entries, sections = [1]) => ({ sections, entries })

  it('moves at once, the whole block with it, and only that slot', async () => {
    api.moveSlot.mockReturnValue(new Promise(() => {}))
    const list = [row(1, 1, P1), row(2, 2, P1), row(3, 3, P1)]
    const { result, read } = setup(list)
    act(() => { result.current.move(slot(list.slice(0, 2), [1, 2]), 11, P2) })
    expect(read().entries.map((e) => e.period_id)).toEqual([12, 12, 11])
    expect(read().entries[0].order).toBe(1)
  })

  it('goes back and offers a way round when refused', async () => {
    api.moveSlot.mockRejectedValue(new Error('400 Taken'))
    const list = [row(1, 1, P1)]
    const { result, read, onMoveRefused } = setup(list)
    await act(async () => { await result.current.move(slot(list), 11, P2) })
    expect(read().entries[0].period_id).toBe(11)
    expect(onMoveRefused.mock.calls[0].slice(0, 3)).toEqual([1, 11, 12])
  })

  it('sends requests one at a time, in order', async () => {
    const first = deferred()
    api.moveSlot.mockReturnValueOnce(first.promise).mockResolvedValue({ entries: [] })
    const list = [row(1, 1, P1), row(2, 2, P1)]
    const { result } = setup(list)
    act(() => {
      result.current.move(slot([list[0]]), 11, P2)
      result.current.move({ sections: [2], entries: [list[1]] }, 11, P2)
    })
    await act(async () => { await Promise.resolve() })
    expect(api.moveSlot).toHaveBeenCalledTimes(1)
    await act(async () => { first.resolve({ entries: [] }); await first.promise })
    await waitFor(() => expect(api.moveSlot).toHaveBeenCalledTimes(2))
    expect(api.moveSlot.mock.calls[1][1]).toBe(2)
  })

  it('a refusal puts back only its own edit', async () => {
    api.moveSlot.mockRejectedValueOnce(new Error('400 No')).mockResolvedValue({ entries: [] })
    const list = [row(1, 1, P1), row(2, 2, P1)]
    const { result, read } = setup(list)
    await act(async () => {
      result.current.move(slot([list[0]]), 11, P2)
      await result.current.move({ sections: [2], entries: [list[1]] }, 11, P2)
    })
    expect(read().entries.find((e) => e.id === 1).period_id).toBe(11)
    expect(read().entries.find((e) => e.id === 2).period_id).toBe(12)
  })
})

describe('taking off, locking and undoing', () => {
  it('takes a slot off at once and puts it back when refused', async () => {
    api.removeSlot.mockRejectedValue(new Error('400 Locked'))
    const list = [row(1, 1, P1)]
    const { result, read, onRefused } = setup(list)
    const pending = act(async () => {
      const done = result.current.remove({ sections: [1], entries: list }, P1)
      expect(read().entries).toEqual([])
      await done
    })
    await pending
    expect(read().entries).toEqual(list)
    expect(onRefused).toHaveBeenCalledTimes(1)
  })

  it('undoes a removal with the same lessons', async () => {
    api.removeSlot.mockResolvedValue({ entries: [], removed_ids: [1] })
    api.restoreSlot.mockResolvedValue({ entries: [row(50, 1, P1)] })
    const list = [row(1, 1, P1, { locked: false })]
    const { result, read } = setup(list)
    await act(async () => { await result.current.remove({ sections: [1], entries: list }, P1) })
    expect(result.current.undoCount).toBe(1)
    await act(async () => { await result.current.undo() })
    expect(api.restoreSlot).toHaveBeenCalledWith(1, list)
    expect(read().entries.map((e) => e.id)).toEqual([50])
    expect(result.current.undoCount).toBe(0)
  })

  it('undoes a placement by taking it off', async () => {
    api.placeLesson.mockResolvedValue({ entries: [row(9, 1, P1)] })
    api.removeSlot.mockResolvedValue({ entries: [], removed_ids: [9] })
    const { result, read } = setup()
    await act(async () => { await result.current.place(lesson, 7, P1, [7]) })
    await act(async () => { await result.current.undo() })
    expect(api.removeSlot).toHaveBeenCalledWith(1, 1, 11)
    expect(read().entries).toEqual([])
  })

  it('undoes a move by moving it back', async () => {
    api.moveSlot.mockResolvedValue({ entries: [] })
    const list = [row(1, 1, P1)]
    const { result, read } = setup(list)
    await act(async () => { await result.current.move({ sections: [1], entries: list }, 11, P2) })
    await act(async () => { await result.current.undo() })
    expect(api.moveSlot).toHaveBeenLastCalledWith(1, 1, 12, 11)
    expect(read().entries[0].period_id).toBe(11)
    expect(result.current.undoCount).toBe(0)
  })

  it('locks at once, unlocks when refused, and undoes', async () => {
    api.lockSlot.mockResolvedValueOnce({ entries: [] })
    const list = [row(1, 1, P1)]
    const { result, read } = setup(list)
    await act(async () => { await result.current.lock({ sections: [1], entries: list }, 1, 11, true) })
    expect(read().entries[0].locked).toBe(true)
    api.lockSlot.mockRejectedValueOnce(new Error('400 No'))
    await act(async () => { await result.current.undo() })
    expect(read().entries[0].locked).toBe(true)
  })

  it('asks for the rule forecast again after a saved edit', async () => {
    api.moveSlot.mockResolvedValue({ entries: [] })
    const list = [row(1, 1, P1)]
    const { result } = setup(list)
    const before = result.current.revision
    await act(async () => { await result.current.move({ sections: [1], entries: list }, 11, P2) })
    expect(result.current.revision).toBe(before + 1)
  })
})
