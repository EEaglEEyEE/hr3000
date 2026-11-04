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
