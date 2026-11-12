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

export type AbsenceRate = components['schemas']['AbsenceRateResponse']
export type Headcount = components['schemas']['HeadcountResponse']
export type AbsenceCategory = components['schemas']['AbsenceType']

export function useAbsenceRateQuery(dateFrom: string, dateTo: string, categories: AbsenceCategory[]) {
  return useQuery({
    queryKey: ['reports', 'absence-rate', dateFrom, dateTo, categories],
    enabled: categories.length > 0 && dateFrom <= dateTo,
    queryFn: async () =>
      unwrap(await apiClient.GET('/reports/absence-rate', { params: { query: { date_from: dateFrom, date_to: dateTo, categories } } })),
  })
}

export function useHeadcountQuery(dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ['reports', 'headcount', dateFrom, dateTo],
    enabled: dateFrom <= dateTo,
    queryFn: async () => unwrap(await apiClient.GET('/reports/headcount', { params: { query: { date_from: dateFrom, date_to: dateTo } } })),
  })
}
