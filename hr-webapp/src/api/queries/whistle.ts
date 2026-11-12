import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'
import { authFetch, failure } from '../documents'

export type WhistleStatus = components['schemas']['WhistleStatus']
export type WhistleCategory = components['schemas']['WhistleCategory']
export type WhistleCaseSummary = components['schemas']['WhistleCaseSummary']
export type WhistleCaseDetail = components['schemas']['WhistleCaseDetail']
export type WhistleOfficeMessage = components['schemas']['WhistleOfficeMessageCreate']
export type WhistleCaseUpdate = components['schemas']['WhistleCaseUpdate']
export type WhistleOfficers = components['schemas']['WhistleOfficersResponse']

/** Ist das Hinweisgebersystem an, bin ich Meldestellen-Beauftragte:r? (Menü, „Mein Bereich“) */
export function useWhistleStatusQuery(enabled = true) {
  return useQuery({
    queryKey: ['whistle', 'status'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/whistle/status')),
  })
}

export function useWhistleCasesQuery(enabled = true) {
  return useQuery({
    queryKey: ['whistle', 'cases'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/whistle/cases')),
  })
}

/** Jeder Abruf wird im Protokoll des Vorgangs vermerkt – daher kein Neuladen beim Fensterwechsel. */
export function useWhistleCaseQuery(caseId: number | null) {
  return useQuery({
    queryKey: ['whistle', 'case', caseId],
    enabled: caseId !== null,
    refetchOnWindowFocus: false,
    queryFn: async () =>
      unwrap(await apiClient.GET('/whistle/cases/{case_id}', { params: { path: { case_id: caseId! } } })),
  })
}

function useCaseUpdate<T>(caseId: number, send: (payload: T) => Promise<WhistleCaseDetail>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: send,
    onSuccess: (detail) => {
      queryClient.setQueryData(['whistle', 'case', caseId], detail)
      void queryClient.invalidateQueries({ queryKey: ['whistle', 'cases'] })
    },
  })
}

export function useWhistleMessageMutation(caseId: number) {
  return useCaseUpdate<WhistleOfficeMessage>(caseId, async (body) =>
    unwrap(await apiClient.POST('/whistle/cases/{case_id}/messages', { params: { path: { case_id: caseId } }, body })),
  )
}

export function useWhistleCaseUpdateMutation(caseId: number) {
  return useCaseUpdate<WhistleCaseUpdate>(caseId, async (body) =>
    unwrap(await apiClient.PATCH('/whistle/cases/{case_id}', { params: { path: { case_id: caseId } }, body })),
  )
}

export function useDeleteWhistleCaseMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (caseId: number) => {
      const result = await apiClient.DELETE('/whistle/cases/{case_id}', { params: { path: { case_id: caseId } } })
      if (result.error !== undefined) unwrap(result)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['whistle'] }),
  })
}

/** Anhang herunterladen (Abruf wird protokolliert). */
export async function downloadWhistleAttachment(caseId: number, attachmentId: number, filename: string): Promise<void> {
  const response = await authFetch(`/api/whistle/cases/${caseId}/attachments/${attachmentId}`)
  if (!response.ok) throw await failure(response, 'Der Anhang konnte nicht geladen werden.')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

// --- Beauftragte benennen (Admin) ---

export function useWhistleOfficersQuery(enabled = true) {
  return useQuery({
    queryKey: ['whistle', 'officers'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/whistle/officers')),
  })
}

function useOfficerMutation(send: (accountId: number) => Promise<WhistleOfficers>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: send,
    onSuccess: (data) => {
      queryClient.setQueryData(['whistle', 'officers'], data)
      void queryClient.invalidateQueries({ queryKey: ['whistle', 'status'] })
    },
  })
}

export function useAppointWhistleOfficerMutation() {
  return useOfficerMutation(async (accountId) =>
    unwrap(await apiClient.POST('/whistle/officers', { body: { account_id: accountId } })),
  )
}

export function useDismissWhistleOfficerMutation() {
  return useOfficerMutation(async (accountId) =>
    unwrap(await apiClient.DELETE('/whistle/officers/{account_id}', { params: { path: { account_id: accountId } } })),
  )
}
