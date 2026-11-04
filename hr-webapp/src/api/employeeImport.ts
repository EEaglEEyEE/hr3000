import { getAccessToken } from '../auth/tokenStore'
import type { components } from './schema'

export type BulkImportResult = components['schemas']['BulkImportResult']

/** Lädt eine Mitarbeiter-CSV hoch – mirrors payrollExport.ts: rohes fetch()
 * statt apiClient, da hier ein multipart/form-data-Body gesendet wird statt
 * JSON (openapi-fetch unterstützt das nicht typisiert). */
export async function uploadEmployeeBulkImport(file: File): Promise<BulkImportResult> {
  const formData = new FormData()
  formData.append('file', file)

  const token = getAccessToken()
  const response = await fetch('/api/employees/bulk-import', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error((body as { detail?: string } | null)?.detail ?? 'Import fehlgeschlagen.')
  }
  return body as BulkImportResult
}
