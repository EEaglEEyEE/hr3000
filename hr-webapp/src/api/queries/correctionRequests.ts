import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type CorrectionRequest = components['schemas']['CorrectionRequestResponse']
export type CorrectionRequestCreate = components['schemas']['CorrectionRequestCreate']
export type CorrectionStatus = components['schemas']['CorrectionRequestStatus']

export function useCorrectionRequestsQuery(status?: CorrectionStatus, enabled = true) {
  return useQuery({
    enabled,
    refetchInterval: status === 'PENDING' ? 60_000 : false,
    queryKey: ['correction-requests', status ?? 'all'],
    queryFn: async () =>
      unwrap(await apiClient.GET('/punch-correction-requests', { params: { query: { status } } })),
  })
}

export function useCreateCorrectionRequestMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: CorrectionRequestCreate) =>
      unwrap(await apiClient.POST('/punch-correction-requests', { body: payload })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['correction-requests'] }),
  })
}

export function useDecideCorrectionRequestMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ requestId, approve, note }: { requestId: number; approve: boolean; note?: string }) =>
      unwrap(
        await apiClient.PATCH('/punch-correction-requests/{request_id}/decide', {
          params: { path: { request_id: requestId } },
          body: { approve, note: note || null },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['correction-requests'] })
      // Übernommene Stempelungen ändern Zeiten, Salden und "Zu klären".
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
      void queryClient.invalidateQueries({ queryKey: ['open-days'] })
    },
  })
}
