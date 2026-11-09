import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type PersonalData = components['schemas']['PersonalDataResponse']
export type PersonalDataInput = components['schemas']['PersonalData']
export type CostCenter = components['schemas']['CostCenterResponse']
export type CostCenterShare = components['schemas']['CostCenterShare']

export function usePersonalDataQuery(employeeId: number) {
  return useQuery({
    queryKey: ['personal-data', employeeId],
    queryFn: async () =>
      unwrap(await apiClient.GET('/employees/{employee_id}/personal-data', { params: { path: { employee_id: employeeId } } })),
  })
}

export function useOwnPersonalDataQuery() {
  return useQuery({
    queryKey: ['personal-data', 'me'],
    queryFn: async () => unwrap(await apiClient.GET('/me/personal-data')),
  })
}

export function useUpdatePersonalDataMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: PersonalDataInput) =>
      unwrap(
        await apiClient.PATCH('/employees/{employee_id}/personal-data', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: (data) => queryClient.setQueryData(['personal-data', employeeId], data),
  })
}

export function useCostCentersQuery(includeArchived = false) {
  return useQuery({
    queryKey: ['cost-centers', includeArchived],
    queryFn: async () =>
      unwrap(await apiClient.GET('/cost-centers', { params: { query: { include_archived: includeArchived } } })),
  })
}

function invalidateCostCenters(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['cost-centers'] })
}

export function useCreateCostCenterMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { code: string; name: string }) =>
      unwrap(await apiClient.POST('/cost-centers', { body: payload })),
    onSuccess: () => invalidateCostCenters(queryClient),
  })
}

export function useUpdateCostCenterMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: { code?: string; name?: string; archived?: boolean } }) =>
      unwrap(await apiClient.PATCH('/cost-centers/{cost_center_id}', { params: { path: { cost_center_id: id } }, body: payload })),
    onSuccess: () => invalidateCostCenters(queryClient),
  })
}

export function useDeleteCostCenterMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const result = await apiClient.DELETE('/cost-centers/{cost_center_id}', { params: { path: { cost_center_id: id } } })
      if (result.error) unwrap(result)
    },
    onSuccess: () => invalidateCostCenters(queryClient),
  })
}

export function useSetEmployeeCostCentersMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (shares: CostCenterShare[]) =>
      unwrap(
        await apiClient.PUT('/employees/{employee_id}/cost-centers', {
          params: { path: { employee_id: employeeId } },
          body: shares,
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees'] }),
  })
}
