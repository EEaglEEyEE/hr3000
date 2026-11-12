import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { components } from './schema'
import { apiClient, unwrap } from './client'
import { getAccessToken } from '../auth/tokenStore'

/** Lädt den Lohn-Export als CSV herunter – mirrors shiftPlanPdf.ts: rohes
 * fetch() statt apiClient, da der Endpoint eine Datei statt JSON liefert. */
export async function downloadPayrollExport(
  employeeIds: number[],
  dateFrom: string,
  dateTo: string,
): Promise<void> {
  const params = new URLSearchParams({ from: dateFrom, to: dateTo })
  employeeIds.forEach((id) => params.append('employee_ids', String(id)))

  const token = getAccessToken()
  const response = await fetch(`/api/payroll-export?${params.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? 'Lohn-Export fehlgeschlagen.')
  }

  const blob = await response.blob()
  const match = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)
  const filename = match?.[1] ?? `lohn-export_${dateFrom}_${dateTo}.csv`

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export type DatevPreview = components['schemas']['DatevPreviewResponse']

function datevParams(employeeIds: number[], month: string): URLSearchParams {
  const params = new URLSearchParams({ month })
  employeeIds.forEach((id) => params.append('employee_ids', String(id)))
  return params
}

/** Vorschau: Buchungen und Hinweise, was nicht übertragen werden kann. */
export async function fetchDatevPreview(employeeIds: number[], month: string): Promise<DatevPreview> {
  return unwrap(
    await apiClient.GET('/payroll-export/datev/preview', { params: { query: { month, employee_ids: employeeIds } } }),
  )
}

/** DATEV-LODAS-Importdatei (Bewegungsdaten des Monats) herunterladen. */
export async function downloadDatevExport(employeeIds: number[], month: string): Promise<void> {
  const response = await authorizedFetch(`/api/payroll-export/datev?${datevParams(employeeIds, month).toString()}`)
  saveBlob(await response.blob(), `datev-lodas_${month}.txt`)
}

/** Datei-Endpunkt mit Anmeldung abrufen; Fehlermeldung des Servers oder fallback. */
export async function authorizedFetch(url: string, fallback = 'DATEV-Export fehlgeschlagen.'): Promise<Response> {
  const token = getAccessToken()
  const response = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
    throw new Error(typeof body?.detail === 'string' ? body.detail : fallback)
  }
  return response
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export type PayrollMonthStatus = components['schemas']['PayrollMonthStatus']

/** Monatsabschluss der Gewählten und bisherige Exporte dieses Monats (Hinweis vor dem Export). */
export function usePayrollMonthStatusQuery(month: string, employeeIds: number[]) {
  return useQuery({
    queryKey: ['payroll-export-status', month, employeeIds],
    queryFn: async () =>
      unwrap(await apiClient.GET('/payroll-export/status', { params: { query: { month, employee_ids: employeeIds } } })),
    enabled: employeeIds.length > 0,
  })
}

export type DatevSettings = components['schemas']['DatevSettings']

/** Berater-/Mandantennummer für DATEV (Berechtigung „Vergütung & Lohn-Export“). */
export function useDatevSettingsQuery() {
  return useQuery({
    queryKey: ['datev-settings'],
    queryFn: async () => unwrap(await apiClient.GET('/payroll-export/datev/settings')),
  })
}

export function useUpdateDatevSettingsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: DatevSettings) => unwrap(await apiClient.PUT('/payroll-export/datev/settings', { body: payload })),
    onSuccess: (data) => queryClient.setQueryData(['datev-settings'], data),
  })
}
