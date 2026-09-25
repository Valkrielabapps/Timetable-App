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

export function useTimetables(schoolId) {
  return useQuery({
    queryKey: keys.timetables(schoolId),
    queryFn: () => api.listTimetables(schoolId),
    enabled: schoolId != null,
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
  return (...updated) => {
    queryClient.setQueryData(keys.timetable(timetableId), (prev) => {
      if (!prev) return prev
      return {
        ...prev,
        entries: prev.entries.map((e) => updated.find((u) => u.id === e.id) ?? e),
      }
    })
  }
}
