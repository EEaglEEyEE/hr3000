import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Device = components['schemas']['DeviceResponse']
export type DeviceCreateRequest = components['schemas']['DeviceCreateRequest']
export type DeviceUpdateRequest = components['schemas']['DeviceUpdateRequest']

export function useDevicesQuery(locationId?: number) {
  return useQuery({
    queryKey: ['devices', locationId],
    queryFn: async () =>
      unwrap(await apiClient.GET('/devices', { params: { query: { location_id: locationId } } })),
  })
}

export function useCreateDeviceMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: DeviceCreateRequest) =>
      unwrap(await apiClient.POST('/devices', { body: payload })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['devices'] })
    },
  })
}

export function useUpdateDeviceMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      deviceId,
      payload,
    }: {
      deviceId: number
      payload: DeviceUpdateRequest
    }) =>
      unwrap(
        await apiClient.PATCH('/devices/{device_id}', {
          params: { path: { device_id: deviceId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['devices'] })
    },
  })
}

export function useDeleteDeviceMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (deviceId: number) => {
      const result = await apiClient.DELETE('/devices/{device_id}', {
        params: { path: { device_id: deviceId } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['devices'] })
    },
  })
}

/** Kurzer Kopplungscode (15 Min., einmalig) zum Einrichten des Tablets. */
export function useCreatePairingCodeMutation() {
  return useMutation({
    mutationFn: async (deviceId: number) =>
      unwrap(
        await apiClient.POST('/devices/{device_id}/pairing-code', {
          params: { path: { device_id: deviceId } },
        }),
      ),
  })
}
