import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Contract = components['schemas']['ContractResponse']
export type ContractCreateRequest = components['schemas']['ContractCreateRequest']
export type Compensation = components['schemas']['CompensationResponse']
export type CompensationCreateRequest = components['schemas']['CompensationCreateRequest']

function throwApiError(result: { error?: unknown; response: Response }): never {
  const detail = result.error as { detail?: string; code?: string }
  throw new ApiError(result.response.status, detail.code, detail.detail ?? 'Löschen fehlgeschlagen.')
}

export function useContractsQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'contracts'],
    queryFn: async () =>
      unwrap(await apiClient.GET('/employees/{employee_id}/contracts', { params: { path: { employee_id: employeeId } } })),
  })
}

export function useCreateContractMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ContractCreateRequest) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/contracts', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'contracts'] }),
  })
}

export function useDeleteContractMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (contractId: number) => {
      const result = await apiClient.DELETE('/employees/{employee_id}/contracts/{contract_id}', {
        params: { path: { employee_id: employeeId, contract_id: contractId } },
      })
      if (result.error !== undefined) throwApiError(result)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'contracts'] }),
  })
}

/** Nur für Administratoren – das Backend liefert sonst 403. */
export function useCompensationQuery(employeeId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['employees', employeeId, 'compensation'],
    enabled,
    // Jeder Abruf wird im Audit-Log protokolliert – nicht bei jedem Fensterwechsel neu laden.
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/compensation', { params: { path: { employee_id: employeeId } } }),
      ),
  })
}

export function useCreateCompensationMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: CompensationCreateRequest) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/compensation', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'compensation'] }),
  })
}

export function useDeleteCompensationMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (compensationId: number) => {
      const result = await apiClient.DELETE('/employees/{employee_id}/compensation/{compensation_id}', {
        params: { path: { employee_id: employeeId, compensation_id: compensationId } },
      })
      if (result.error !== undefined) throwApiError(result)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'compensation'] }),
  })
}
