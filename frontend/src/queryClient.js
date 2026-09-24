import { QueryClient } from '@tanstack/react-query'

/**
 * Shared React Query client.
 *
 * Replaces the pattern in App.jsx where one `loadSchoolData` fetched ten
 * endpoints at once and eight different mutation handlers called it again
 * afterwards - so adding a single class group re-fetched teachers, periods,
 * rooms, constraints, members, invites, timetables and requirements, then
 * replaced all of it and re-rendered the whole tree. That round trip is the
 * lag; caching each resource separately means a mutation only invalidates
 * what it actually changed.
 *
 * Defaults worth knowing:
 *
 * - `staleTime: 30s` - school setup data (subjects, teachers, periods)
 *   changes when someone in this tab changes it, not on its own. Treating it
 *   as fresh for half a minute stops a tab switch from re-fetching lists the
 *   app already has. Mutations invalidate explicitly, so this never serves
 *   data that is stale because of something *we* did.
 * - `retry: 1` - the default of 3 turns a genuine 4xx into three round trips
 *   before the user sees the error. Retrying auth and validation failures is
 *   pointless; one retry covers a flaky connection.
 * - `refetchOnWindowFocus: false` - an admin alt-tabbing to a staff
 *   spreadsheet and back should not trigger a wave of refetches. Real
 *   freshness comes from invalidation after mutations.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

/**
 * Query keys in one place, so an invalidation and a fetch can't disagree
 * about the shape of a key - a mismatch there fails silently, leaving the
 * screen stale with no error to notice.
 *
 * Every school-scoped key carries the school id, which is what keeps two
 * schools' data from bleeding into one another when an admin switches
 * between them.
 */
export const keys = {
  schools: () => ['schools'],
  classGroups: (schoolId) => ['classGroups', schoolId],
  teachers: (schoolId) => ['teachers', schoolId],
  subjects: (schoolId) => ['subjects', schoolId],
  periods: (schoolId) => ['periods', schoolId],
  rooms: (schoolId) => ['rooms', schoolId],
  constraints: (schoolId) => ['constraints', schoolId],
  members: (schoolId) => ['members', schoolId],
  invites: (schoolId) => ['invites', schoolId],
  timetables: (schoolId) => ['timetables', schoolId],
  timetable: (timetableId) => ['timetable', timetableId],
  requirements: (schoolId) => ['requirements', schoolId],
}
