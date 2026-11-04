import { useQuery } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Plan = components['schemas']['PlanResponse']

/** Tarif und Auslastung. Liegt unter ['employees', …], damit jede Mitarbeiteränderung ihn neu lädt. */
export function usePlanQuery(enabled = true) {
  return useQuery({
    queryKey: ['employees', 'plan'],
    queryFn: async () => unwrap(await apiClient.GET('/plan')),
    enabled,
  })
}

export const PLAN_LABELS: Record<Plan['plan'], string> = {
  FREE: 'Kostenlos',
  PAID: 'Abo',
  UNLIMITED: 'Unbegrenzt',
}
