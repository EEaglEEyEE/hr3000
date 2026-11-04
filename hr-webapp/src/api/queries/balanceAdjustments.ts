import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type BalanceAdjustment = components['schemas']['BalanceAdjustmentResponse']
export type BalanceAdjustmentCreate = components['schemas']['BalanceAdjustmentCreateRequest']

export function useBalanceAdjustmentsQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'balance-adjustments'],
    queryFn: async () =>
      unwrap(await apiClient.GET('/employees/{employee_id}/balance-adjustments', { params: { path: { employee_id: employeeId } } })),
  })
}

function useInvalidate(employeeId: number) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['employees', employeeId] })
    void queryClient.invalidateQueries({ queryKey: ['reports'] })
  }
}

export function useCreateBalanceAdjustmentMutation(employeeId: number) {
  const invalidate = useInvalidate(employeeId)
  return useMutation({
    mutationFn: async (payload: BalanceAdjustmentCreate) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/balance-adjustments', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useDeleteBalanceAdjustmentMutation(employeeId: number) {
  const invalidate = useInvalidate(employeeId)
  return useMutation({
    mutationFn: async (adjustmentId: number) => {
      const result = await apiClient.DELETE('/employees/{employee_id}/balance-adjustments/{adjustment_id}', {
        params: { path: { employee_id: employeeId, adjustment_id: adjustmentId } },
      })
      if (result.error !== undefined) {
        const detail = result.error as { detail?: unknown; code?: string }
        throw new ApiError(result.response.status, detail.code, typeof detail.detail === 'string' ? detail.detail : 'Löschen fehlgeschlagen.')
      }
    },
    onSuccess: invalidate,
  })
}
