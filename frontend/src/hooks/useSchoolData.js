import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api'
import { keys } from '../queryClient'

/**
 * Per-resource data hooks.
 *
 * These replace App.jsx's lifted `useState` + one big `loadSchoolData`
 * fetching ten endpoints. The problem with that shape was not the initial
 * load - it was that eight mutation handlers called `loadSchoolData` again
 * afterwards, so adding one room re-fetched teachers, constraints, invites
 * and everything else, then replaced all of it.
 *
 * Here a mutation invalidates only the key it actually affected, so the
 * network cost of an edit is proportional to the edit.
 *
 * Every hook takes `schoolId` and is disabled while it is null - the app
 * renders before a school is selected, and `enabled` is what stops a burst
 * of requests for `undefined` on first paint.
 */

// ---------------------------------------------------------------------------
// Rooms
// ---------------------------------------------------------------------------

export function useRooms(schoolId) {
  return useQuery({
    queryKey: keys.rooms(schoolId),
    queryFn: () => api.listRooms(schoolId),
    enabled: schoolId != null,
  })
}

export function useRoomMutations(schoolId) {
  const queryClient = useQueryClient()
  // Invalidate rather than hand-patch the cached array: the server owns
  // ids, defaults and any normalisation, and a locally-patched list drifts
  // from what a refetch would return. The refetch is one endpoint, which is
  // the entire point of the change.
  const invalidate = () => queryClient.invalidateQueries({ queryKey: keys.rooms(schoolId) })

  const create = useMutation({
    mutationFn: (data) => api.createRoom(data),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id) => api.deleteRoom(id),
    onSuccess: invalidate,
  })

  return {
    // Kept promise-returning and shaped like the old callbacks so the panels
    // don't have to change at the same time as the data layer - mutateAsync
    // rejects on failure, which is what their try/catch already expects.
    create: (data) => create.mutateAsync(data),
    delete: (id) => remove.mutateAsync(id),
  }
}

// ---------------------------------------------------------------------------
// Timetables
// ---------------------------------------------------------------------------

/**
 * Which timetables this school has, WITHOUT their entries.
 *
 * Used to find one - the newest, or the draft - which is then fetched by id
 * through useTimetable below. The response used to carry every entry of every
 * timetable ever generated: 4MB and 71 queries on a 28-section school with ten
 * generations, to read an id. That was the few-second pause on every visit to
 * the Timetable tab, and it grew with every generation.
 *
 * Now that it is a few hundred bytes, it is held far longer. Timetables appear
 * when one is generated, which this tab does itself and invalidates - the only
 * other source is another admin generating one, and showing that a few minutes
 * late costs nothing next to re-fetching on every tab switch.
 */
export function useTimetables(schoolId) {
  return useQuery({
    queryKey: keys.timetables(schoolId),
    queryFn: () => api.listTimetables(schoolId),
    enabled: schoolId != null,
    staleTime: 5 * 60_000,
  })
}

/**
 * One timetable, polled while the solver is still working on it.
 *
 * Generation runs as a background job on the server (see the module
 * docstring in backend/app/routers/timetables.py), so the row appears with
 * status="generating" and flips to "draft" or "failed" later. This replaces
 * a hand-rolled setInterval + ref + manual clear in App.jsx: the interval
 * here is derived from the data, so it starts and stops on its own and
 * cannot leak past an unmount or a school switch.
 */
export function useTimetable(timetableId) {
  return useQuery({
    queryKey: keys.timetable(timetableId),
    queryFn: () => api.getTimetable(timetableId),
    enabled: timetableId != null,
    // `false` stops the polling. Returning the interval straight from the
    // status means a reload mid-generation resumes polling with no special
    // case for it - the query just sees "generating" and carries on.
    refetchInterval: (query) => (query.state.data?.status === 'generating' ? 1500 : false),
    // TimetableTab unmounts on every tab switch, so polling pauses while the
    // admin is elsewhere. A row still marked "generating" is therefore
    // untrustworthy the moment they come back and must be re-read; a
    // finished one is not, and re-fetching it would pull hundreds of entry
    // rows on every tab switch - and would also discard the entry patches
    // applied by useApplyEntryUpdates below.
    staleTime: (query) => (query.state.data?.status === 'generating' ? 0 : 30_000),
  })
}

export function useGenerateTimetable(schoolId) {
  const queryClient = useQueryClient()
  const generate = useMutation({
    mutationFn: () => api.generateTimetable(schoolId),
    onSuccess: (created) => {
      // Seed the cache with the row the server just returned so the polling
      // query starts from it rather than waiting a round trip to discover a
      // timetable it was already handed.
      queryClient.setQueryData(keys.timetable(created.id), created)
      queryClient.invalidateQueries({ queryKey: keys.timetables(schoolId) })
    },
  })
  return { generate: () => generate.mutateAsync(), isGenerating: generate.isPending }
}

/**
 * Patch specific entries into the cached timetable after a lock/move/swap.
 *
 * Deliberately not an invalidation. PATCH and swap return exactly the rows
 * that changed, and re-fetching a school-wide timetable (hundreds of rows)
 * to reflect one lock toggle is what used to make that toggle take 5-10
 * seconds to show its new state.
 */
export function useApplyEntryUpdates(timetableId) {
  const queryClient = useQueryClient()
  return ({ entries = [], violations }) => {
    queryClient.setQueryData(keys.timetable(timetableId), (prev) => {
      if (!prev) return prev
      return {
        ...prev,
        entries: prev.entries.map((e) => entries.find((u) => u.id === e.id) ?? e),
        // Recomputed server-side with every edit and patched in alongside the
        // rows. Left out, the warning band would go stale the moment a slot
        // moved - which is exactly when it has something to say.
        violations: violations ?? prev.violations,
      }
    })
  }
}

/**
 * Move a whole slot in the cache before the server has agreed to it.
 *
 * Dragging used to wait for the round trip before the cell moved, so every
 * drag cost one API call of visible lag on something that should feel like
 * picking a card up and putting it down.
 *
 * The unit is the slot - one section's period - not an entry, matching
 * POST /timetables/{id}/move-slot. An elective block has one entry per option
 * and a split lab one per batch, and they always move together. Whatever is
 * already in the target comes back the other way, so a move into a free cell,
 * a swap of two lessons and a block trading places with a lesson are all the
 * same operation, applied in one cache write so nothing is ever briefly shown
 * twice.
 *
 * Returns a rollback. The move is a guess - the server can still refuse it,
 * usually because the target double-books a teacher - and putting the cells
 * back is the only honest response to that.
 */
export function useOptimisticSlotMove(timetableId) {
  const queryClient = useQueryClient()
  return (classGroupId, fromPeriod, toPeriod) => {
    const key = keys.timetable(timetableId)
    const previous = queryClient.getQueryData(key)
    const at = (period) => ({
      period_id: period.id,
      day_of_week: period.day_of_week,
      order: period.order,
    })
    queryClient.setQueryData(key, (prev) => {
      if (!prev) return prev
      return {
        ...prev,
        entries: prev.entries.map((e) => {
          if (e.class_group_id !== classGroupId) return e
          if (e.period_id === fromPeriod.id) return { ...e, ...at(toPeriod) }
          if (e.period_id === toPeriod.id) return { ...e, ...at(fromPeriod) }
          return e
        }),
        // Deliberately not guessed at. Working out which rules the move breaks
        // would mean a second implementation of the rule engine in the
        // browser, and two of those drifting apart is worse than a banner that
        // settles a moment late. The server sends the real answer back.
        violations: prev.violations,
      }
    })
    return () => queryClient.setQueryData(key, previous)
  }
}

// ---------------------------------------------------------------------------
// Elective blocks
// ---------------------------------------------------------------------------

/**
 * Every elective block in the school, each with its options.
 *
 * School-wide rather than per section: the Plan page switches sections
 * without a round trip, and the Timetable tab needs every section's blocks at
 * once to offer each one's student timetables.
 */
export function useElectiveBlocks(schoolId) {
  return useQuery({
    queryKey: keys.electiveBlocks(schoolId),
    queryFn: () => api.listElectiveBlocks(schoolId),
    enabled: schoolId != null,
  })
}

export function useElectiveBlockMutations(schoolId) {
  const queryClient = useQueryClient()
  // Invalidated, not patched: the server validates the whole set of options
  // against the section's other subjects and blocks, and the row it settles on
  // is the one to show.
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: keys.electiveBlocks(schoolId) })

  const create = useMutation({
    mutationFn: (data) => api.createElectiveBlock(data),
    onSuccess: invalidate,
  })
  const update = useMutation({
    mutationFn: ({ id, data }) => api.updateElectiveBlock(id, data),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (id) => api.deleteElectiveBlock(id),
    onSuccess: invalidate,
  })

  return {
    create: (data) => create.mutateAsync(data),
    update: (id, data) => update.mutateAsync({ id, data }),
    delete: (id) => remove.mutateAsync(id),
    // Deleting a subject removes it from every block (and a block left empty),
    // and deleting a teacher clears them as an option's preferred teacher -
    // both server-side, so the cached blocks have to be re-read afterwards.
    invalidate,
  }
}
