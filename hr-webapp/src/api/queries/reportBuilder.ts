/** Eigene Berichte (Berichts-Builder): Positivliste, Vorschau, gespeicherte Berichte, CSV.
 * Spalten, Filter und Rechte prüft das Backend (app/services/report_builder_service.py). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../client'
import type { components } from '../schema'
import { getAccessToken } from '../../auth/tokenStore'

type Schemas = components['schemas']
export type ReportCatalog = Schemas['CatalogResponse']
export type CatalogSource = Schemas['CatalogSource']
export type CatalogColumn = Schemas['CatalogColumn']
export type ReportDefinition = Schemas['ReportDefinition']
export type ReportFilter = Schemas['ReportFilter']
export type ReportResult = Schemas['ReportResult']
export type SavedReport = Schemas['SavedReportResponse']
export type SavedReportRequest = Schemas['SavedReportRequest']
export type SourceKey = ReportDefinition['source']
export type Operator = ReportFilter['operator']

export interface RunPeriod {
  date_from?: string
  date_to?: string
  page: number
  page_size: number
}

export function useReportCatalogQuery(enabled = true) {
  return useQuery({
    queryKey: ['report-builder', 'catalog'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/report-builder/catalog')),
  })
}

export function useSavedReportsQuery(enabled = true) {
  return useQuery({
    queryKey: ['report-builder', 'reports'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/report-builder/reports')),
  })
}

/** Vorschau einer (ungespeicherten) Definition oder Lauf eines gespeicherten Berichts. */
export async function runReport(definition: ReportDefinition, period: RunPeriod, reportId?: number): Promise<ReportResult> {
  if (reportId !== undefined) {
    return unwrap(
      await apiClient.POST('/report-builder/reports/{report_id}/run', { params: { path: { report_id: reportId } }, body: period }),
    )
  }
  return unwrap(await apiClient.POST('/report-builder/preview', { body: { ...period, definition } }))
}

export function useSaveReportMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id?: number; body: SavedReportRequest }) =>
      id === undefined
        ? unwrap(await apiClient.POST('/report-builder/reports', { body }))
        : unwrap(await apiClient.PUT('/report-builder/reports/{report_id}', { params: { path: { report_id: id } }, body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-builder', 'reports'] }),
  })
}

export function useDeleteReportMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const result = await apiClient.DELETE('/report-builder/reports/{report_id}', { params: { path: { report_id: id } } })
      if (result.error !== undefined) unwrap(result)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-builder', 'reports'] }),
  })
}

/** CSV vom Server (UTF-8 mit BOM, Semikolon, entschärfte Formeln) herunterladen – rohes fetch(),
 * weil der Endpoint eine Datei statt JSON liefert (wie der Lohn-Export). */
export async function downloadReportCsv(definition: ReportDefinition, period: RunPeriod, reportId?: number): Promise<void> {
  const url = reportId === undefined ? '/api/report-builder/export' : `/api/report-builder/reports/${reportId}/export`
  const body = reportId === undefined ? { ...period, definition } : period
  const token = getAccessToken()
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as { detail?: unknown; code?: string } | null
    throw new ApiError(response.status, error?.code, typeof error?.detail === 'string' ? error.detail : 'CSV-Export fehlgeschlagen.')
  }
  const blob = await response.blob()
  const filename = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] ?? 'bericht.csv'
  const link = document.createElement('a')
  const objectUrl = URL.createObjectURL(blob)
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}
