import { useQuery } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type AuditLogEntry = components['schemas']['AuditLogEntryResponse']
export type AuditAction = components['schemas']['AuditAction']

export function useAuditLogQuery(filters: { entityType?: string; from?: string; to?: string }) {
  return useQuery({
    queryKey: ['audit-log', filters],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/audit-log', {
          params: {
            query: {
              entity_type: filters.entityType,
              from: filters.from,
              to: filters.to,
              limit: 500,
            },
          },
        }),
      ),
  })
}
