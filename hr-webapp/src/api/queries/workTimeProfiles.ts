import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type WorkTimeProfile = components['schemas']['WorkTimeProfileResponse']
export type WorkTimeProfileVersion = components['schemas']['WorkTimeProfileVersionResponse']
export type WorkTimeProfileCreateRequest = components['schemas']['WorkTimeProfileCreateRequest']
export type WorkTimeProfileSetRequest = components['schemas']['WorkTimeProfileSetRequest']
export type WorkTimeProfileUpdateRequest = components['schemas']['WorkTimeProfileUpdateRequest']

/** Eine Modelländerung wirkt auf alle zugewiesenen Mitarbeiter: Soll, Salden, Kalender, „Zu klären“. */
function invalidateAll(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['work-time-profiles'] })
  void queryClient.invalidateQueries({ queryKey: ['employees'] })
  void queryClient.invalidateQueries({ queryKey: ['timesheet-overview'] })
  void queryClient.invalidateQueries({ queryKey: ['open-days'] })
  void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
}

/** Arbeitszeitmodelle des Mandanten (mit heute gültiger Fassung und zugewiesenen Mitarbeitern). */
export function useWorkTimeProfilesQuery({ includeArchived = false, enabled = true } = {}) {
  return useQuery({
    queryKey: ['work-time-profiles', { includeArchived }],
    queryFn: async () =>
      unwrap(await apiClient.GET('/work-time-profiles', { params: { query: { include_archived: includeArchived } } })),
    enabled,
  })
}

export function useWorkTimeProfileHistoryQuery(profileId: number | null) {
  return useQuery({
    queryKey: ['work-time-profiles', profileId, 'history'],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/work-time-profiles/{profile_id}/history', {
          params: { path: { profile_id: profileId! } },
        }),
      ),
    enabled: profileId !== null,
  })
}

export function useCreateWorkTimeProfileMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: WorkTimeProfileCreateRequest) =>
      unwrap(await apiClient.POST('/work-time-profiles', { body: payload })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['work-time-profiles'] }),
  })
}

/** Neue Fassung ab Stichtag – gilt für alle zugewiesenen Mitarbeiter. */
export function useSetWorkTimeProfileModelMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ profileId, payload }: { profileId: number; payload: WorkTimeProfileSetRequest }) =>
      unwrap(
        await apiClient.PUT('/work-time-profiles/{profile_id}/model', {
          params: { path: { profile_id: profileId } },
          body: payload,
        }),
      ),
    onSuccess: () => invalidateAll(queryClient),
  })
}

export function useUpdateWorkTimeProfileMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ profileId, payload }: { profileId: number; payload: WorkTimeProfileUpdateRequest }) =>
      unwrap(
        await apiClient.PATCH('/work-time-profiles/{profile_id}', {
          params: { path: { profile_id: profileId } },
          body: payload,
        }),
      ),
    // Name erscheint auch am Mitarbeiter
    onSuccess: () => invalidateAll(queryClient),
  })
}

export function useDeleteWorkTimeProfileMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (profileId: number) => {
      const result = await apiClient.DELETE('/work-time-profiles/{profile_id}', {
        params: { path: { profile_id: profileId } },
      })
      if (result.error) unwrap(result)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['work-time-profiles'] }),
  })
}

/** Modell einem Mitarbeiter ab Stichtag zuweisen. */
export function useAssignWorkTimeProfileMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { profile_id: number; valid_from: string }) =>
      unwrap(
        await apiClient.PUT('/employees/{employee_id}/work-time-profile', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['employees', employeeId] })
      void queryClient.invalidateQueries({ queryKey: ['work-time-profiles'] })
      void queryClient.invalidateQueries({ queryKey: ['timesheet-overview'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}
