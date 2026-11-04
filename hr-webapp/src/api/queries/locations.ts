import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Location = components['schemas']['LocationResponse']
export type LocationCreateRequest = components['schemas']['LocationCreateRequest']
export type LocationUpdateRequest = components['schemas']['LocationUpdateRequest']
export type Bundesland = components['schemas']['Bundesland']

export function useLocationsQuery() {
  return useQuery({
    queryKey: ['locations'],
    queryFn: async () => unwrap(await apiClient.GET('/locations')),
  })
}

export function useCreateLocationMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: LocationCreateRequest) =>
      unwrap(await apiClient.POST('/locations', { body: payload })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['locations'] })
    },
  })
}

export function useUpdateLocationMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      locationId,
      payload,
    }: {
      locationId: number
      payload: LocationUpdateRequest
    }) =>
      unwrap(
        await apiClient.PATCH('/locations/{location_id}', {
          params: { path: { location_id: locationId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['locations'] })
    },
  })
}
