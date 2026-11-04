import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type WorkTimeModel = components['schemas']['WorkTimeModelResponse']
export type WorkTimeModelSetRequest = components['schemas']['WorkTimeModelSetRequest']

export function useFeaturesQuery() {
  return useQuery({
    queryKey: ['features'],
    queryFn: async () => unwrap(await apiClient.GET('/features')),
    staleTime: 60_000,
  })
}

export function useWorkTimeModelQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'work-time-model'],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/work-time-model', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
  })
}

export function useSetWorkTimeModelMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: WorkTimeModelSetRequest) =>
      unwrap(
        await apiClient.PUT('/employees/{employee_id}/work-time-model', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      // Soll/Ist, Kalender, Saldo und Standard-Schichten hängen alle am Modell.
      void queryClient.invalidateQueries({ queryKey: ['employees', employeeId] })
      void queryClient.invalidateQueries({ queryKey: ['timesheet-overview'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export type WorkTimeModelVersion = components['schemas']['WorkTimeModelVersion']

/** Alle Fassungen des Arbeitszeitmodells (neueste zuerst). */
export function useWorkTimeModelHistoryQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'work-time-model', 'history'],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/work-time-model/history', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
  })
}

function invalidateModel(queryClient: ReturnType<typeof useQueryClient>, employeeId: number) {
  void queryClient.invalidateQueries({ queryKey: ['employees', employeeId] })
  void queryClient.invalidateQueries({ queryKey: ['timesheet-overview'] })
  void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
}

export function useUpdateWorkTimeModelVersionMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ versionId, payload }: { versionId: number; payload: WorkTimeModelSetRequest }) =>
      unwrap(
        await apiClient.PUT('/employees/{employee_id}/work-time-model/versions/{version_id}', {
          params: { path: { employee_id: employeeId, version_id: versionId } },
          body: payload,
        }),
      ),
    onSuccess: () => invalidateModel(queryClient, employeeId),
  })
}

export function useDeleteWorkTimeModelVersionMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (versionId: number) => {
      const result = await apiClient.DELETE('/employees/{employee_id}/work-time-model/versions/{version_id}', {
        params: { path: { employee_id: employeeId, version_id: versionId } },
      })
      if (result.error) unwrap(result)
    },
    onSuccess: () => invalidateModel(queryClient, employeeId),
  })
}
