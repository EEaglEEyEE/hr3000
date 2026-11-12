import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type TimeEntryWeek = components['schemas']['TimeEntryWeek']
export type TimeEntryDay = components['schemas']['TimeEntryDay']
export type TimeSpanOut = components['schemas']['TimeSpanOut']
export type TimeEntryCreate = components['schemas']['TimeEntryCreate']
export type TimeSpanIn = components['schemas']['TimeSpanIn']

/** Stundenzettel „Mein Bereich“: Spannen, offene Anträge und Ist je Tag (from–to, höchstens 31 Tage). */
export function useOwnTimeEntriesQuery(from: string, to: string, enabled = true) {
  return useQuery({
    enabled,
    queryKey: ['time-entries', from, to],
    queryFn: async () => unwrap(await apiClient.GET('/me/time-entries', { params: { query: { from, to } } })),
  })
}

/** Eintragen, Zurückziehen und Löschen ändern Zeiten, Konto, Anträge und „Zu klären“. */
function invalidateTimes(queryClient: QueryClient) {
  for (const key of ['time-entries', 'correction-requests', 'employees', 'open-days', 'dashboard', 'punches']) {
    void queryClient.invalidateQueries({ queryKey: [key] })
  }
}

export function useCreateTimeEntryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: TimeEntryCreate) => unwrap(await apiClient.POST('/me/time-entries', { body: payload })),
    onSuccess: () => invalidateTimes(queryClient),
  })
}

export function useWithdrawTimeEntryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (requestId: number) =>
      unwrap(await apiClient.DELETE('/me/time-entries/requests/{request_id}', { params: { path: { request_id: requestId } } })),
    onSuccess: () => invalidateTimes(queryClient),
  })
}

export function useDeleteTimeEntryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (punchId: number) =>
      unwrap(await apiClient.DELETE('/me/time-entries/{punch_id}', { params: { path: { punch_id: punchId } } })),
    onSuccess: () => invalidateTimes(queryClient),
  })
}
