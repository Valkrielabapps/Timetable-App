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
