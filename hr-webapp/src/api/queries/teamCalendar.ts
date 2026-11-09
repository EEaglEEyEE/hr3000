import { useQuery } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type TeamCalendarEmployee = components['schemas']['TeamCalendarEmployee']
export type TeamCalendarDay = components['schemas']['TeamCalendarDay']

export function useTeamCalendarQuery(from: string, to: string, locationId?: number, teamIds: number[] = [], own = false) {
  return useQuery({
    queryKey: ['team-calendar', own ? 'me' : 'all', from, to, locationId, teamIds],
    queryFn: async () =>
      own
        ? // „Mein Bereich“: eigenes Team, Art bei Kollegen nur bei „farbig“
          unwrap(await apiClient.GET('/me/team-calendar', { params: { query: { from, to } } }))
        : unwrap(
            await apiClient.GET('/team-calendar', {
              params: { query: { from, to, location_id: locationId, team_id: teamIds.length ? teamIds : undefined } },
            }),
          ),
  })
}
