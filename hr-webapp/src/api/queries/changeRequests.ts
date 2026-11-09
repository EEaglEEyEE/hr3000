import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type ChangeRequest = components['schemas']['ChangeRequestResponse']
export type ChangeProposal = components['schemas']['ChangeProposal']

export function useChangeRequestsQuery(enabled = true) {
  return useQuery({
    queryKey: ['change-requests'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/change-requests', { params: { query: { status: 'PENDING' } } })),
  })
}

export function useDecideChangeRequestMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, approve, note }: { id: number; approve: boolean; note?: string }) =>
      unwrap(
        await apiClient.POST('/change-requests/{request_id}/decide', {
          params: { path: { request_id: id } },
          body: { approve, note: note || null },
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['change-requests'] }),
  })
}

export function useMyChangeRequestsQuery() {
  return useQuery({
    queryKey: ['my-change-requests'],
    queryFn: async () => unwrap(await apiClient.GET('/me/change-requests')),
  })
}

export function useProposeChangeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ChangeProposal) => unwrap(await apiClient.POST('/me/change-requests', { body: payload })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['my-change-requests'] }),
  })
}
