import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { keys } from '../queryClient'

/**
 * The selected school's plan, lifecycle status (free / active / grace /
 * expired), limits and usage, from GET /api/schools/{id}/entitlements.
 * Used by Settings > Plan & billing and the renewal banner.
 */
export function useEntitlements(schoolId) {
  return useQuery({
    queryKey: keys.entitlements(schoolId),
    queryFn: () => api.getEntitlements(schoolId),
    enabled: schoolId != null,
  })
}
