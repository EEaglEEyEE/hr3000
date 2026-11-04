import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type SupervisorTeamAssignment = components['schemas']['SupervisorTeamAssignmentResponse']
export type SupervisorTeamAssignmentCreateRequest =
  components['schemas']['SupervisorTeamAssignmentCreateRequest']

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['supervisor-team-assignments'] })
}

export function useSupervisorTeamAssignmentsQuery(teamId?: number) {
  return useQuery({
    queryKey: ['supervisor-team-assignments', teamId],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/supervisor-team-assignments', {
          params: { query: { team_id: teamId } },
        }),
      ),
  })
}

export function useCreateSupervisorTeamAssignmentMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: SupervisorTeamAssignmentCreateRequest) =>
      unwrap(await apiClient.POST('/supervisor-team-assignments', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useDeleteSupervisorTeamAssignmentMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (assignmentId: number) => {
      const result = await apiClient.DELETE('/supervisor-team-assignments/{assignment_id}', {
        params: { path: { assignment_id: assignmentId } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => invalidate(queryClient),
  })
}
