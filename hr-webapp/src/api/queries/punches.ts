import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Punch = components['schemas']['PunchResponse']
export type PunchCorrectionRequest = components['schemas']['PunchCorrectionRequest']
export type PunchCreateRequest = components['schemas']['PunchCreateRequest']
export type OwnPunchRequest = components['schemas']['OwnPunchRequest']

export function useEmployeePunchesQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'punches'],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/punches', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
  })
}

function invalidatePunchRelatedQueries(queryClient: ReturnType<typeof useQueryClient>, employeeId: number) {
  void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'punches'] })
  void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'timesheet'] })
  void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'weekly-balance'] })
  void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'overtime-balance'] })
  void queryClient.invalidateQueries({ queryKey: ['open-days'] })
}

export function useCreatePunchMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: PunchCreateRequest) =>
      unwrap(await apiClient.POST('/punches', { body: payload })),
    onSuccess: () => {
      invalidatePunchRelatedQueries(queryClient, employeeId)
    },
  })
}

export function useDeletePunchMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (punchId: number) => {
      const result = await apiClient.DELETE('/punches/{punch_id}', {
        params: { path: { punch_id: punchId } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => {
      invalidatePunchRelatedQueries(queryClient, employeeId)
    },
  })
}

export function useCorrectPunchMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      punchId,
      payload,
    }: {
      punchId: number
      payload: PunchCorrectionRequest
    }) =>
      unwrap(
        await apiClient.PATCH('/punches/{punch_id}', {
          params: { path: { punch_id: punchId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      invalidatePunchRelatedQueries(queryClient, employeeId)
    },
  })
}

/** Stempeln über den Web-Login (Startseite) – Serverzeit, nur für sich selbst. Die Position wird nur
 * mitgeschickt, wenn die Firma den Standort beim Stempeln prüft (sie wird nie gespeichert). */
export function useOwnPunchMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: OwnPunchRequest) => unwrap(await apiClient.POST('/me/punches', { body })),
    // Bis das Dashboard neu geladen ist, bleiben die Knöpfe gesperrt – sonst steht kurz noch der alte Status da.
    onSuccess: async () => {
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
      void queryClient.invalidateQueries({ queryKey: ['open-days'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}
