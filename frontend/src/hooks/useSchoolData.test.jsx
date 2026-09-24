import React from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api'
import { useRoomMutations, useRooms } from './useSchoolData'

vi.mock('../api', () => ({
  api: {
    listRooms: vi.fn(),
    createRoom: vi.fn(),
    deleteRoom: vi.fn(),
    listTeachers: vi.fn(),
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
