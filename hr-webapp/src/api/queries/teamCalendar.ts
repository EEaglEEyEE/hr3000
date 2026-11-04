import { useQuery } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type TeamCalendarEmployee = components['schemas']['TeamCalendarEmployee']
export type TeamCalendarDay = components['schemas']['TeamCalendarDay']

export function useTeamCalendarQuery(from: string, to: string, locationId?: number, teamIds: number[] = []) {
  return useQuery({
    queryKey: ['team-calendar', from, to, locationId, teamIds],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/team-calendar', {
          params: { query: { from, to, location_id: locationId, team_id: teamIds.length ? teamIds : undefined } },
        }),
      ),
  })
}
