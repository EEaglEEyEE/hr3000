import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type LeaveEntitlement = components['schemas']['LeaveEntitlementResponse']
export type LeaveEntitlementUpdateRequest = components['schemas']['LeaveEntitlementUpdateRequest']

export function useLeaveEntitlementQuery(employeeId: number, year: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'leave-entitlement', year],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/leave-entitlement', {
          params: { path: { employee_id: employeeId }, query: { year } },
        }),
      ),
  })
}

export function useUpdateLeaveEntitlementMutation(employeeId: number, year: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: LeaveEntitlementUpdateRequest) =>
      unwrap(
        await apiClient.PATCH('/employees/{employee_id}/leave-entitlement', {
          params: { path: { employee_id: employeeId }, query: { year } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ['employees', employeeId, 'leave-entitlement', year],
      })
    },
  })
}

export type LeaveAdjustment = components['schemas']['LeaveAdjustmentResponse']

/** Korrekturen am Urlaubskonto eines Jahres (± Tage, ggf. mit Verfall). */
export function useLeaveAdjustmentsQuery(employeeId: number, year: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'leave-adjustments', year],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/leave-adjustments', {
          params: { path: { employee_id: employeeId }, query: { year } },
        }),
      ),
  })
}

function useInvalidateLeave(employeeId: number) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'leave-adjustments'] })
    void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'leave-entitlement'] })
  }
}

export function useCreateLeaveAdjustmentMutation(employeeId: number) {
  const invalidate = useInvalidateLeave(employeeId)
  return useMutation({
    mutationFn: async (payload: components['schemas']['LeaveAdjustmentCreateRequest']) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/leave-adjustments', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useDeleteLeaveAdjustmentMutation(employeeId: number) {
  const invalidate = useInvalidateLeave(employeeId)
  return useMutation({
    mutationFn: async (adjustmentId: number) => {
      await apiClient.DELETE('/employees/{employee_id}/leave-adjustments/{adjustment_id}', {
        params: { path: { employee_id: employeeId, adjustment_id: adjustmentId } },
      })
    },
    onSuccess: invalidate,
  })
}
