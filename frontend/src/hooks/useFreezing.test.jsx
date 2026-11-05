import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { markSubjectFrozen, useSetFrozen, useSubjectFreezeActions } from './useSchoolData'

vi.mock('../api', () => ({
  api: { setFrozen: vi.fn(), freezeSubject: vi.fn(), unfreezeSubject: vi.fn(), listLessons: vi.fn(() => Promise.resolve([])) },
}))

/**
 * Freezing has to show on the click. These hold the screen to that: nothing
 * waits for the server, a refusal puts things back, and quick clicks can't
 * leave the screen showing an older answer than the last click.
 */

const STATUS = ['frozenStatus', 1, 9]
const FREEZES = ['subjectFreezes', 1, 9]
const TIMETABLE = ['timetable', 9]
const row = (id, frozen = false) => ({ class_group_id: id, frozen, stale_reason: null })
const deferred = () => {
  let resolve, reject
  const promise = new Promise((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}

function setup(hook, seed = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(STATUS, seed.status ?? [row(1), row(2)])
  client.setQueryData(FREEZES, seed.freezes ?? [])
  client.setQueryData(TIMETABLE, { id: 9, entries: seed.entries ?? [] })
  const wrapper = ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(hook, { wrapper })
  return { result, client }
}

beforeEach(() => vi.clearAllMocks())

describe('freezing a section', () => {
  const hook = () => useSetFrozen(1, 9)

  it('shows at once, before the server answers', async () => {
    api.setFrozen.mockReturnValue(new Promise(() => {}))
    const { result, client } = setup(hook)
    act(() => { result.current.setFrozen([1], true) })
    await waitFor(() => expect(client.getQueryData(STATUS)[0].frozen).toBe(true))
    expect(client.getQueryData(STATUS)[1].frozen).toBe(false)
  })

  it('unfreezes at once too, clearing what it said about being frozen', async () => {
    api.setFrozen.mockReturnValue(new Promise(() => {}))
    const { result, client } = setup(hook, { status: [{ ...row(1, true), frozen_from: 'Version 1', stale_reason: 'Old' }] })
    act(() => { result.current.setFrozen([1], false) })
    await waitFor(() => expect(client.getQueryData(STATUS)[0]).toMatchObject({ frozen: false, frozen_from: null, stale_reason: null }))
  })

  it('takes the server’s answer when it comes', async () => {
    api.setFrozen.mockResolvedValue([{ ...row(1, true), frozen_from: 'Version 2' }, row(2)])
    const { result, client } = setup(hook)
    await act(async () => { await result.current.setFrozen([1], true) })
    expect(client.getQueryData(STATUS)[0].frozen_from).toBe('Version 2')
  })

  it('puts it back when refused, and lets the caller say why', async () => {
    api.setFrozen.mockRejectedValue(new Error('Nothing to keep yet'))
    const { result, client } = setup(hook)
    await act(async () => {
      await expect(result.current.setFrozen([1], true)).rejects.toThrow('Nothing to keep yet')
    })
    expect(client.getQueryData(STATUS)[0].frozen).toBe(false)
  })

  it('handles quick clicks in order, without an older answer showing', async () => {
    const first = deferred()
    const second = deferred()
    api.setFrozen.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result, client } = setup(hook)
    act(() => {
      result.current.setFrozen([1], true)
      result.current.setFrozen([2], true)
    })
    await waitFor(() => expect(client.getQueryData(STATUS).map((r) => r.frozen)).toEqual([true, true]))
    await waitFor(() => expect(api.setFrozen).toHaveBeenCalledTimes(1))
    // The first answer only knows about the first click, so it isn't shown.
    await act(async () => { first.resolve([row(1, true), row(2)]); await first.promise })
    await waitFor(() => expect(api.setFrozen).toHaveBeenCalledTimes(2))
    expect(client.getQueryData(STATUS).map((r) => r.frozen)).toEqual([true, true])
    await act(async () => { second.resolve([{ ...row(1, true), frozen_from: 'V' }, row(2, true)]); await second.promise })
    await waitFor(() => expect(client.getQueryData(STATUS)[0].frozen_from).toBe('V'))
  })
})

describe('freezing a subject', () => {
  const hook = () => useSubjectFreezeActions(1, 9)
  const lesson = (id, section, subject, more = {}) => ({ id, class_group_id: section, subject_id: subject, elective_block_id: null, subject_frozen: false, ...more })
  const shown = { subject: 'Physics', sectionIds: [1], scopeLabel: 'Grade 9' }
  const body = { subject_id: 5, scope: 'grades', grades: ['Grade 9'], class_group_ids: null, block_mode: 'subject' }

  it('lists it and marks its lessons at once, without reading the timetable again', async () => {
    api.freezeSubject.mockReturnValue(new Promise(() => {}))
    const { result, client } = setup(hook, { entries: [lesson(1, 1, 5), lesson(2, 2, 5), lesson(3, 1, 6)] })
    const refetch = vi.spyOn(client, 'invalidateQueries')
    act(() => { result.current.freeze(body, shown) })
    await waitFor(() => expect(client.getQueryData(FREEZES)).toHaveLength(1))
    expect(client.getQueryData(FREEZES)[0]).toMatchObject({ subject: 'Physics', scope_label: 'Grade 9', section_count: 1, pending: true })
    expect(client.getQueryData(TIMETABLE).entries.map((e) => e.subject_frozen)).toEqual([true, false, false])
    expect(refetch.mock.calls.flat().some((c) => c?.queryKey?.[0] === 'timetable')).toBe(false)
  })

  it('takes it all back when refused', async () => {
    api.freezeSubject.mockRejectedValue(new Error('No lessons yet'))
    const { result, client } = setup(hook, { entries: [lesson(1, 1, 5)] })
    await act(async () => {
      await expect(result.current.freeze(body, shown)).rejects.toThrow('No lessons yet')
    })
    expect(client.getQueryData(FREEZES)).toEqual([])
    expect(client.getQueryData(TIMETABLE).entries[0].subject_frozen).toBe(false)
  })

  it('unfreezes at once, and comes back if refused', async () => {
    const freeze = { id: 3, subject_id: 5, class_group_ids: [1], block_mode: 'subject' }
    const answer = deferred()
    api.unfreezeSubject.mockReturnValue(answer.promise)
    const { result, client } = setup(hook, { freezes: [freeze], entries: [lesson(1, 1, 5, { subject_frozen: true })] })
    let pending
    act(() => { pending = result.current.unfreeze(3) })
    await waitFor(() => expect(client.getQueryData(FREEZES)).toEqual([]))
    expect(client.getQueryData(TIMETABLE).entries[0].subject_frozen).toBe(false)
    await act(async () => {
      answer.reject(new Error('No'))
      await expect(pending).rejects.toThrow('No')
    })
    expect(client.getQueryData(FREEZES)).toEqual([freeze])
    expect(client.getQueryData(TIMETABLE).entries[0].subject_frozen).toBe(true)
  })
})

describe('which lessons a subject freeze keeps', () => {
  const physics = { id: 1, class_group_id: 1, subject_id: 5, elective_block_id: 4, subject_frozen: false }
  const accounts = { id: 2, class_group_id: 1, subject_id: 6, elective_block_id: 4, subject_frozen: false }
  const other = { id: 3, class_group_id: 2, subject_id: 5, elective_block_id: 4, subject_frozen: false }

  it('keeps just the subject', () => {
    const out = markSubjectFrozen([physics, accounts, other], [{ subject_id: 5, class_group_ids: [1], block_mode: 'subject' }])
    expect(out.map((e) => e.subject_frozen)).toEqual([true, false, false])
  })

  it('keeps the whole block when asked', () => {
    const out = markSubjectFrozen([physics, accounts, other], [{ subject_id: 5, class_group_ids: [1], block_mode: 'block' }])
    expect(out.map((e) => e.subject_frozen)).toEqual([true, true, false])
  })

  it('leaves unchanged lessons as they are, so their grids don’t redraw', () => {
    const out = markSubjectFrozen([physics, accounts], [{ subject_id: 5, class_group_ids: [1], block_mode: 'subject' }])
    expect(out[0]).not.toBe(physics)
    expect(out[1]).toBe(accounts)
  })
})
