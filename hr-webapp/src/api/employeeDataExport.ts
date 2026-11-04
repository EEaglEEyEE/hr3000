import { getAccessToken } from '../auth/tokenStore'

/** Lädt den DSGVO-Datenexport (Art. 15) eines Mitarbeiters als JSON-Datei
 * herunter – mirrors payrollExport.ts: rohes fetch() statt apiClient, da der
 * Endpoint eine Datei statt eines typisierten JSON-Bodys liefert. */
export async function downloadEmployeeDataExport(employeeId: number): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(`/api/employees/${employeeId}/data-export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? 'Datenexport fehlgeschlagen.')
  }

  const blob = await response.blob()
  const match = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)
  const filename = match?.[1] ?? `datenexport_${employeeId}.json`

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
