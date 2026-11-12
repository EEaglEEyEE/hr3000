import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'
import { authFetch, failure } from '../documents'

export type Absence = components['schemas']['AbsenceResponse']
export type AbsenceCreateRequest = components['schemas']['AbsenceCreateRequest']
export type AbsenceUpdateRequest = components['schemas']['AbsenceUpdateRequest']
export type AbsenceDecideRequest = components['schemas']['AbsenceDecideRequest']

export function usePendingAbsencesQuery(enabled = true) {
  return useQuery({
    enabled,
    queryKey: ['absences', 'pending'],
    queryFn: async () => unwrap(await apiClient.GET('/absences/pending')),
  })
}

export function useDecideAbsenceMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      absenceId,
      payload,
    }: {
      absenceId: number
      payload: AbsenceDecideRequest
    }) =>
      unwrap(
        await apiClient.PATCH('/absences/{absence_id}/decide', {
          params: { path: { absence_id: absenceId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['absences', 'pending'] })
      invalidateAbsenceEffects(queryClient)
    },
  })
}

export function useEmployeeAbsencesQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'absences'],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/absences', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
  })
}

/** Nachweis (z. B. AU-Bescheinigung) zu einer Abwesenheit hochladen – landet in der Personalakte. */
export function useUploadAbsenceCertificateMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ absenceId, file }: { absenceId: number; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      const response = await authFetch(`/api/absences/${absenceId}/certificate`, { method: 'POST', body: form })
      if (!response.ok) throw await failure(response, 'Upload fehlgeschlagen.')
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'absences'] })
      void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'documents'] })
    },
  })
}

/** Wer aus dem Team im Zeitraum abwesend ist (Mitarbeiter: nur mit Einstellung, ohne Art). */
export function useTeamOverlapsQuery(employeeId: number, from: string, to: string, enabled: boolean) {
  return useQuery({
    queryKey: ['employees', employeeId, 'team-overlaps', from, to],
    enabled: enabled && Boolean(from) && Boolean(to) && from <= to,
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/team-overlaps', {
          params: { path: { employee_id: employeeId }, query: { from, to } },
        }),
      ),
  })
}

/** Wer als Vertretung infrage kommt (aktive Kolleginnen und Kollegen, nur Namen). */
export function useSubstituteCandidatesQuery(employeeId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['employees', employeeId, 'substitute-candidates'],
    enabled,
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/substitute-candidates', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
  })
}

/** Eine Abwesenheit ändert Resturlaub, Saldo, Kalender, Startseite und "Zu klären" mit. */
function invalidateAbsenceEffects(queryClient: QueryClient, employeeId?: number) {
  void queryClient.invalidateQueries({ queryKey: employeeId === undefined ? ['employees'] : ['employees', employeeId] })
  for (const key of ['open-days', 'dashboard', 'team-calendar', 'timesheet-overview', 'period-closures']) {
    void queryClient.invalidateQueries({ queryKey: [key] })
  }
}

function useInvalidateAbsences(employeeId: number) {
  const queryClient = useQueryClient()
  return () => invalidateAbsenceEffects(queryClient, employeeId)
}

export function useCreateAbsenceMutation(employeeId: number) {
  const invalidate = useInvalidateAbsences(employeeId)
  return useMutation({
    mutationFn: async (payload: AbsenceCreateRequest) =>
      unwrap(await apiClient.POST('/absences', { body: payload })),
    onSuccess: invalidate,
  })
}

export function useUpdateAbsenceMutation(employeeId: number) {
  const invalidate = useInvalidateAbsences(employeeId)
  return useMutation({
    mutationFn: async ({
      absenceId,
      payload,
    }: {
      absenceId: number
      payload: AbsenceUpdateRequest
    }) =>
      unwrap(
        await apiClient.PATCH('/absences/{absence_id}', {
          params: { path: { absence_id: absenceId } },
          body: payload,
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useDeleteAbsenceMutation(employeeId: number) {
  const invalidate = useInvalidateAbsences(employeeId)
  return useMutation({
    mutationFn: async (absenceId: number) => {
      const result = await apiClient.DELETE('/absences/{absence_id}', {
        params: { path: { absence_id: absenceId } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: invalidate,
  })
}
