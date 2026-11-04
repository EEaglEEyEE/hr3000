import { useQuery } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type AbsenceStats = components['schemas']['AbsenceStatsResponse']
export type AttentionItem = components['schemas']['AttentionItem']

export function useAbsenceStatsQuery(year: number) {
  return useQuery({
    queryKey: ['reports', 'absence-stats', year],
    queryFn: async () => unwrap(await apiClient.GET('/reports/absence-stats', { params: { query: { year } } })),
  })
}

export function useVacationReportQuery(year: number) {
  return useQuery({
    queryKey: ['reports', 'vacation', year],
    queryFn: async () => unwrap(await apiClient.GET('/reports/vacation', { params: { query: { year } } })),
  })
}

export function useOvertimeReportQuery() {
  return useQuery({
    queryKey: ['reports', 'overtime'],
    queryFn: async () => unwrap(await apiClient.GET('/reports/overtime')),
  })
}

export function useAttentionQuery() {
  return useQuery({
    queryKey: ['reports', 'attention'],
    queryFn: async () => unwrap(await apiClient.GET('/reports/attention')),
  })
}

export function useLaborCostsQuery(from: string, to: string, enabled: boolean) {
  return useQuery({
    queryKey: ['reports', 'labor-costs', from, to],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/reports/labor-costs', { params: { query: { from, to } } })),
  })
}
