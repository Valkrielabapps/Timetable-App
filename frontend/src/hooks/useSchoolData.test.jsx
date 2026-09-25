import React from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api'
import {
  useApplyEntryUpdates,
  useGenerateTimetable,
  useRoomMutations,
  useRooms,
  useTimetable,
} from './useSchoolData'

vi.mock('../api', () => ({
  api: {
    listRooms: vi.fn(),
    createRoom: vi.fn(),
    deleteRoom: vi.fn(),
    listTeachers: vi.fn(),
    listTimetables: vi.fn(),
    getTimetable: vi.fn(),
    generateTimetable: vi.fn(),
  },
}))

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const Wrapper = ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { Wrapper, client }
}

describe('useRooms', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listRooms.mockResolvedValue([{ id: 1, name: 'Lab 1' }])
  })

  it('fetches rooms for the school', async () => {
    const { Wrapper } = wrapper()
    const { result } = renderHook(() => useRooms(7), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([{ id: 1, name: 'Lab 1' }])
    expect(api.listRooms).toHaveBeenCalledWith(7)
  })

  it('does not fetch before a school is selected', () => {
    // The app renders before selectedSchoolId resolves; without `enabled`
    // this fires a request for null on first paint.
    const { Wrapper } = wrapper()
    renderHook(() => useRooms(null), { wrapper: Wrapper })
    expect(api.listRooms).not.toHaveBeenCalled()
  })

  it('caches per school, so switching schools does not show the wrong rooms', async () => {
    const { Wrapper } = wrapper()
    const { result, rerender } = renderHook(({ id }) => useRooms(id), {
      wrapper: Wrapper,
      initialProps: { id: 7 },
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    api.listRooms.mockResolvedValue([{ id: 2, name: 'Hall' }])
    rerender({ id: 8 })

    await waitFor(() => expect(result.current.data).toEqual([{ id: 2, name: 'Hall' }]))
    expect(api.listRooms).toHaveBeenLastCalledWith(8)
  })
})

describe('useRoomMutations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listRooms.mockResolvedValue([])
    api.createRoom.mockResolvedValue({ id: 9, name: 'New' })
    api.deleteRoom.mockResolvedValue(undefined)
  })

  it('refetches rooms after a create - and nothing else', async () => {
    // The whole point of the migration: adding a room used to re-fetch
    // teachers, constraints, invites and six other endpoints.
    const { Wrapper } = wrapper()
    const { result } = renderHook(
      () => ({ rooms: useRooms(7), mutations: useRoomMutations(7) }),
      { wrapper: Wrapper },
    )
    await waitFor(() => expect(result.current.rooms.isSuccess).toBe(true))
    expect(api.listRooms).toHaveBeenCalledTimes(1)

    await result.current.mutations.create({ school_id: 7, name: 'New' })

    await waitFor(() => expect(api.listRooms).toHaveBeenCalledTimes(2))
    expect(api.listTeachers).not.toHaveBeenCalled()
  })

  it('refetches rooms after a delete', async () => {
    const { Wrapper } = wrapper()
    const { result } = renderHook(
      () => ({ rooms: useRooms(7), mutations: useRoomMutations(7) }),
      { wrapper: Wrapper },
    )
    await waitFor(() => expect(result.current.rooms.isSuccess).toBe(true))

    await result.current.mutations.delete(1)
    await waitFor(() => expect(api.listRooms).toHaveBeenCalledTimes(2))
  })

  it('rejects on failure, so existing try/catch in the panels still works', async () => {
    api.createRoom.mockRejectedValue(new Error('409 duplicate'))
    const { Wrapper } = wrapper()
    const { result } = renderHook(() => useRoomMutations(7), { wrapper: Wrapper })

    await expect(result.current.create({ school_id: 7, name: 'x' })).rejects.toThrow('409 duplicate')
  })
})

describe('useTimetable polling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  // Fake timers leak into later describes otherwise, and waitFor depends on
  // real ones - the failure looks like a broken assertion, not a timer bug.
  afterEach(() => vi.useRealTimers())

  it('keeps polling while the solver is still working', async () => {
    // Generation is a background job on the server, so the row appears as
    // "generating" and flips later. This replaces a hand-rolled setInterval.
    api.getTimetable.mockResolvedValue({ id: 3, status: 'generating', entries: [] })
    const { Wrapper } = wrapper()
    const { result } = renderHook(() => useTimetable(3), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.getTimetable).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1600)
    await waitFor(() => expect(api.getTimetable).toHaveBeenCalledTimes(2))
  })

  it('stops polling once the timetable is done', async () => {
    api.getTimetable.mockResolvedValue({ id: 3, status: 'draft', entries: [] })
    const { Wrapper } = wrapper()
    const { result } = renderHook(() => useTimetable(3), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const callsWhenDone = api.getTimetable.mock.calls.length

    await vi.advanceTimersByTimeAsync(5000)
    expect(api.getTimetable).toHaveBeenCalledTimes(callsWhenDone)
  })

  it('stops as soon as a poll returns a finished timetable', async () => {
    api.getTimetable
      .mockResolvedValueOnce({ id: 3, status: 'generating', entries: [] })
      .mockResolvedValue({ id: 3, status: 'draft', entries: [] })
    const { Wrapper } = wrapper()
    const { result } = renderHook(() => useTimetable(3), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.data?.status).toBe('generating'))
    await vi.advanceTimersByTimeAsync(1600)
    await waitFor(() => expect(result.current.data?.status).toBe('draft'))

    const settled = api.getTimetable.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.getTimetable).toHaveBeenCalledTimes(settled)
  })

  it('does not poll when there is no timetable yet', () => {
    const { Wrapper } = wrapper()
    renderHook(() => useTimetable(null), { wrapper: Wrapper })
    expect(api.getTimetable).not.toHaveBeenCalled()
  })
})

describe('useApplyEntryUpdates', () => {
  beforeEach(() => vi.clearAllMocks())

  it('patches the returned entries without re-fetching', async () => {
    // Re-fetching a school-wide timetable to reflect one lock toggle is what
    // made that toggle take 5-10 seconds.
    api.getTimetable.mockResolvedValue({
      id: 3,
      status: 'draft',
      entries: [
        { id: 1, locked: false },
        { id: 2, locked: false },
      ],
    })
    const { Wrapper, client } = wrapper()
    const { result } = renderHook(
      () => ({ tt: useTimetable(3), apply: useApplyEntryUpdates(3) }),
      { wrapper: Wrapper },
    )
    await waitFor(() => expect(result.current.tt.isSuccess).toBe(true))
    const callsBefore = api.getTimetable.mock.calls.length

    result.current.apply({ id: 2, locked: true })

    const cached = client.getQueryData(['timetable', 3])
    expect(cached.entries.find((e) => e.id === 2).locked).toBe(true)
    // Untouched entries keep their state - the patch is targeted, not a
    // wholesale replace.
    expect(cached.entries.find((e) => e.id === 1).locked).toBe(false)
    expect(api.getTimetable).toHaveBeenCalledTimes(callsBefore)
  })
})

describe('useGenerateTimetable', () => {
  beforeEach(() => vi.clearAllMocks())

  it('seeds the cache so polling starts from the returned row', async () => {
    api.generateTimetable.mockResolvedValue({ id: 9, status: 'generating', entries: [] })
    api.getTimetable.mockResolvedValue({ id: 9, status: 'generating', entries: [] })
    api.listTimetables.mockResolvedValue([{ id: 9 }])

    const { Wrapper } = wrapper()
    const { result } = renderHook(() => useGenerateTimetable(7), { wrapper: Wrapper })
    const created = await result.current.generate()

    expect(created.id).toBe(9)
    expect(api.generateTimetable).toHaveBeenCalledWith(7)
  })
})
