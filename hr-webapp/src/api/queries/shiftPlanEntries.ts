import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type ShiftPlanEntry = components['schemas']['ShiftPlanEntryResponse']
export type ShiftPlanEntryUpsertRequest = components['schemas']['ShiftPlanEntryUpsertRequest']
export type EffectiveShiftDay = components['schemas']['EffectiveShiftDayResponse']

function invalidate(queryClient: ReturnType<typeof useQueryClient>, employeeId: number) {
  void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'shift-plan-entries'] })
  void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'effective-shifts'] })
}

export function useShiftPlanEntriesQuery(employeeId: number, from: string, to: string) {
  return useQuery({
    queryKey: ['employees', employeeId, 'shift-plan-entries', from, to],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/shift-plan-entries', {
          params: { path: { employee_id: employeeId }, query: { from, to } },
        }),
      ),
  })
}

export function useEffectiveShiftsQuery(employeeId: number, from: string, to: string) {
  return useQuery({
    queryKey: ['employees', employeeId, 'effective-shifts', from, to],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/effective-shifts', {
          params: { path: { employee_id: employeeId }, query: { from, to } },
        }),
      ),
  })
}

export function useUpsertShiftPlanEntryMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      date,
      payload,
    }: {
      date: string
      payload: ShiftPlanEntryUpsertRequest
    }) =>
      unwrap(
        await apiClient.PUT('/employees/{employee_id}/shift-plan-entries/{entry_date}', {
          params: { path: { employee_id: employeeId, entry_date: date } },
          body: payload,
        }),
      ),
    onSuccess: () => invalidate(queryClient, employeeId),
  })
}

export function useDeleteShiftPlanEntryMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (date: string) => {
      const result = await apiClient.DELETE('/employees/{employee_id}/shift-plan-entries/{entry_date}', {
        params: { path: { employee_id: employeeId, entry_date: date } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => invalidate(queryClient, employeeId),
  })
}
