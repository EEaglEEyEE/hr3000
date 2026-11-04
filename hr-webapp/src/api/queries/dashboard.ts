import { useQuery } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Dashboard = components['schemas']['DashboardResponse']
export type DashboardEvent = components['schemas']['DashboardEvent']

export const DASHBOARD_RANGES = [7, 14, 30, 90]
export const DASHBOARD_RANGE_KEY = 'hr3000.dashboard_days'

/** Zuletzt gewählter Zeitraum für "Nächste Termine" (pro Browser gemerkt). */
export function initialDashboardRange(): number {
  try {
    const value = Number(localStorage.getItem(DASHBOARD_RANGE_KEY))
    return DASHBOARD_RANGES.includes(value) ? value : 30
  } catch {
    return 30
  }
}

/** Dürfen Mitarbeiter selbst Abwesenheiten beantragen? Teilt sich den Cache mit der Startseite. */
export function useAbsenceRequestsEnabled(): boolean {
  return useDashboardQuery(initialDashboardRange()).data?.absence_requests_enabled ?? true
}

/** days = wie weit "Nächste Termine" in die Zukunft reichen (ab heute). */
export function useDashboardQuery(days: number) {
  return useQuery({
    queryKey: ['dashboard', days],
    queryFn: async () => unwrap(await apiClient.GET('/dashboard', { params: { query: { days } } })),
    refetchInterval: 60_000,
    placeholderData: (previous) => previous,
  })
}
