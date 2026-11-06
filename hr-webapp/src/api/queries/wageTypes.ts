import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type WageTypeItem = components['schemas']['WageTypeItemResponse']
export type PayComponentType = components['schemas']['PayComponentTypeResponse']
export type PayComponentTypeCreateRequest = components['schemas']['PayComponentTypeCreateRequest']
export type PayComponentTypeUpdateRequest = components['schemas']['PayComponentTypeUpdateRequest']

/** Lohnart je Zeitart (gearbeitete Stunden, Urlaub, Krankheit, …). Nur Admin. */
export function useWageTypesQuery() {
  return useQuery({
    queryKey: ['wage-types'],
    queryFn: async () => unwrap(await apiClient.GET('/wage-types')),
  })
}

export function useUpdateWageTypesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (items: Record<string, string | null>) =>
      unwrap(await apiClient.PUT('/wage-types', { body: { items } as never })),
    onSuccess: (data) => queryClient.setQueryData(['wage-types'], data),
  })
}

/** Katalog der Zulagen- und Einmalzahlungsarten. Nur Admin. */
export function usePayComponentTypesQuery(enabled = true) {
  return useQuery({
    queryKey: ['pay-component-types'],
    queryFn: async () => unwrap(await apiClient.GET('/pay-component-types')),
    enabled,
  })
}

function invalidateTypes(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['pay-component-types'] })
  // Name/Lohnart der Art erscheinen an den Zulagen der Mitarbeiter
  void queryClient.invalidateQueries({ queryKey: ['employees'] })
}

export function useCreatePayComponentTypeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: PayComponentTypeCreateRequest) =>
      unwrap(await apiClient.POST('/pay-component-types', { body: payload })),
    onSuccess: () => invalidateTypes(queryClient),
  })
}

export function useUpdatePayComponentTypeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: PayComponentTypeUpdateRequest }) =>
      unwrap(await apiClient.PATCH('/pay-component-types/{type_id}', { params: { path: { type_id: id } }, body: payload })),
    onSuccess: () => invalidateTypes(queryClient),
  })
}

export function useDeletePayComponentTypeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const result = await apiClient.DELETE('/pay-component-types/{type_id}', { params: { path: { type_id: id } } })
      if (result.error) unwrap(result)
    },
    onSuccess: () => invalidateTypes(queryClient),
  })
}
