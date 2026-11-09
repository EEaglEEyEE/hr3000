import { useQuery } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type TeamCalendarEmployee = components['schemas']['TeamCalendarEmployee']
export type TeamCalendarDay = components['schemas']['TeamCalendarDay']

/** departmentIds: Abteilungen samt Unterabteilungen (leer = alle sichtbaren; 0 = ohne Abteilung). */
export function useTeamCalendarQuery(from: string, to: string, locationId?: number, departmentIds: number[] = [], own = false) {
  return useQuery({
    queryKey: ['team-calendar', own ? 'me' : 'all', from, to, locationId, departmentIds],
    queryFn: async () =>
      own
        ? // „Mein Bereich“: eigene Abteilung, Art bei Kollegen nur bei „farbig“
          unwrap(await apiClient.GET('/me/team-calendar', { params: { query: { from, to } } }))
        : unwrap(
            await apiClient.GET('/team-calendar', {
              params: { query: { from, to, location_id: locationId, department_id: departmentIds.length ? departmentIds : undefined } },
            }),
          ),
  })
}
