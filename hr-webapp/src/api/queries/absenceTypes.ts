import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type AbsenceTypeDef = components['schemas']['AbsenceTypeResponse']
export type AbsenceTypeCreateRequest = components['schemas']['AbsenceTypeCreateRequest']
export type AbsenceTypeUpdateRequest = components['schemas']['AbsenceTypeUpdateRequest']

export function useAbsenceTypesQuery() {
  return useQuery({
    queryKey: ['absence-types'],
    queryFn: async () => unwrap(await apiClient.GET('/absence-types')),
    staleTime: 5 * 60_000,
  })
}

/** Abwesenheitsarten nach ID – für Namen/Farben in Kalendern und Listen. */
export function useAbsenceTypeMap(): Map<number, AbsenceTypeDef> {
  const { data } = useAbsenceTypesQuery()
  return useMemo(() => new Map((data ?? []).map((type) => [type.id, type])), [data])
}

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['absence-types'] })
}

export function useCreateAbsenceTypeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: AbsenceTypeCreateRequest) =>
      unwrap(await apiClient.POST('/absence-types', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useUpdateAbsenceTypeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ typeId, payload }: { typeId: number; payload: Partial<AbsenceTypeUpdateRequest> }) =>
      unwrap(
        await apiClient.PATCH('/absence-types/{type_id}', {
          params: { path: { type_id: typeId } },
          body: { clear_certificate_from_day: false, ...payload },
        }),
      ),
    onSuccess: () => invalidate(queryClient),
  })
}
