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
    /** replaceBound: Tablet ist schon mit einem Gerät verbunden – der Code tauscht es aus (nach Rückfrage). */
    mutationFn: async ({ deviceId, replaceBound = false }: { deviceId: number; replaceBound?: boolean }) =>
      unwrap(
        await apiClient.POST('/devices/{device_id}/pairing-code', {
          params: { path: { device_id: deviceId } },
          body: { replace_bound: replaceBound },
        }),
      ),
  })
}

// --- Verteilung per MDM ------------------------------------------------------------------------

export type EnrollmentKey = components['schemas']['EnrollmentKeyResponse']
export type CreatedEnrollmentKey = components['schemas']['EnrollmentKeyCreatedResponse']
export type DeviceEnrollment = components['schemas']['DeviceEnrollmentResponse']

export function useEnrollmentKeysQuery() {
  return useQuery({
    queryKey: ['enrollment-keys'],
    queryFn: async () => unwrap(await apiClient.GET('/devices/enrollment-keys')),
  })
}

/** Neuer Registrierungsschlüssel für einen Standort (ersetzt einen vorhandenen). valid_days null = unbefristet. */
export function useCreateEnrollmentKeyMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { location_id: number; valid_days: number | null }) =>
      unwrap(await apiClient.POST('/devices/enrollment-keys', { body: payload })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['enrollment-keys'] })
    },
  })
}

export function useDeleteEnrollmentKeyMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (locationId: number) => {
      const result = await apiClient.DELETE('/devices/enrollment-keys/{location_id}', {
        params: { path: { location_id: locationId } },
      })
      if (result.error !== undefined) throw new Error('Sperren fehlgeschlagen.')
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['enrollment-keys'] })
    },
  })
}

/** Geräte, die auf Freigabe warten – regelmäßig nachladen, damit neue Anfragen ohne Neuladen erscheinen. */
export function useEnrollmentsQuery() {
  return useQuery({
    queryKey: ['device-enrollments'],
    queryFn: async () => unwrap(await apiClient.GET('/devices/enrollments')),
    refetchInterval: 30_000,
  })
}

export function useApproveEnrollmentMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      enrollmentId,
      payload,
    }: {
      enrollmentId: number
      payload: { device_id?: number | null; name?: string | null }
    }) =>
      unwrap(
        await apiClient.POST('/devices/enrollments/{enrollment_id}/approve', {
          params: { path: { enrollment_id: enrollmentId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['device-enrollments'] })
      void queryClient.invalidateQueries({ queryKey: ['devices'] })
    },
  })
}

/** Alle Anfragen entfernen, deren Gerät sich nicht mehr meldet (verwaist). */
export function useRemoveInactiveEnrollmentsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrap(await apiClient.POST('/devices/enrollments/remove-inactive')),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['device-enrollments'] })
    },
  })
}

export function useRejectEnrollmentMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (enrollmentId: number) => {
      const result = await apiClient.DELETE('/devices/enrollments/{enrollment_id}', {
        params: { path: { enrollment_id: enrollmentId } },
      })
      if (result.error !== undefined) throw new Error('Ablehnen fehlgeschlagen.')
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['device-enrollments'] })
    },
  })
}
