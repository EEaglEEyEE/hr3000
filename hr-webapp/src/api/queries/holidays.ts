import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Holiday = components['schemas']['HolidayResponse']
export type HolidayCreateRequest = components['schemas']['HolidayCreateRequest']
export type HolidayUpdateRequest = components['schemas']['HolidayUpdateRequest']
export type HolidayImportRequest = components['schemas']['HolidayImportRequest']
export type HolidayImportResponse = components['schemas']['HolidayImportResponse']

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['holidays'] })
}

export function useHolidaysQuery(year?: number, locationId?: number) {
  return useQuery({
    queryKey: ['holidays', year, locationId],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/holidays', { params: { query: { year, location_id: locationId } } }),
      ),
  })
}

export function useCreateHolidayMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: HolidayCreateRequest) =>
      unwrap(await apiClient.POST('/holidays', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useUpdateHolidayMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ holidayId, payload }: { holidayId: number; payload: HolidayUpdateRequest }) =>
      unwrap(
        await apiClient.PATCH('/holidays/{holiday_id}', {
          params: { path: { holiday_id: holidayId } },
          body: payload,
        }),
      ),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useImportHolidaysMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: HolidayImportRequest) =>
      unwrap(await apiClient.POST('/holidays/import', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useDeleteHolidayMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (holidayId: number) => {
      const result = await apiClient.DELETE('/holidays/{holiday_id}', {
        params: { path: { holiday_id: holidayId } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => invalidate(queryClient),
  })
}
