import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type EmployeeDefaultShift = components['schemas']['EmployeeDefaultShiftResponse']
export type EmployeeDefaultShiftCreateRequest = components['schemas']['EmployeeDefaultShiftCreateRequest']
export type EmployeeDefaultShiftUpdateRequest = components['schemas']['EmployeeDefaultShiftUpdateRequest']

function invalidate(queryClient: ReturnType<typeof useQueryClient>, employeeId: number) {
  void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'default-shifts'] })
}

export function useDefaultShiftsQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'default-shifts'],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/default-shifts', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
  })
}

export function useCreateDefaultShiftMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: EmployeeDefaultShiftCreateRequest) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/default-shifts', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: () => invalidate(queryClient, employeeId),
  })
}

export function useDeleteDefaultShiftMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (defaultShiftId: number) => {
      const result = await apiClient.DELETE('/employees/{employee_id}/default-shifts/{default_id}', {
        params: { path: { employee_id: employeeId, default_id: defaultShiftId } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => invalidate(queryClient, employeeId),
  })
}
