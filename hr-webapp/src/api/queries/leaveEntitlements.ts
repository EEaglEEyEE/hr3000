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
