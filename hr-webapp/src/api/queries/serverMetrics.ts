import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type ServerMetrics = components['schemas']['ServerMetricsResponse']
export type ServerMetricPoint = components['schemas']['ServerMetricPointResponse']
export type ServerMetricsRange = ServerMetrics['range']

/** Super-Admin: Server-Auslastung mit Verlauf; jede Minute neu (so oft wird gemessen). */
export function useServerMetricsQuery(range: ServerMetricsRange) {
  return useQuery({
    queryKey: ['platform', 'server-metrics', range],
    queryFn: async () => unwrap(await apiClient.GET('/platform/server-metrics', { params: { query: { range } } })),
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
  })
}
