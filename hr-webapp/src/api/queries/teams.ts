import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Team = components['schemas']['TeamResponse']
export type TeamCreateRequest = components['schemas']['TeamCreateRequest']
export type TeamUpdateRequest = components['schemas']['TeamUpdateRequest']

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['teams'] })
}

export function useTeamsQuery() {
  return useQuery({
    queryKey: ['teams'],
    queryFn: async () => unwrap(await apiClient.GET('/teams')),
  })
}

export function useCreateTeamMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: TeamCreateRequest) =>
      unwrap(await apiClient.POST('/teams', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useUpdateTeamMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ teamId, payload }: { teamId: number; payload: TeamUpdateRequest }) =>
      unwrap(
        await apiClient.PATCH('/teams/{team_id}', {
          params: { path: { team_id: teamId } },
          body: payload,
        }),
      ),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useDeleteTeamMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (teamId: number) => {
      const result = await apiClient.DELETE('/teams/{team_id}', {
        params: { path: { team_id: teamId } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => invalidate(queryClient),
  })
}
