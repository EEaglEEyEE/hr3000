import { getAccessToken } from '../auth/tokenStore'

function extractFilename(contentDisposition: string | null, fallback: string): string {
  const match = contentDisposition?.match(/filename="([^"]+)"/)
  return match?.[1] ?? fallback
}

/** Lädt den Schichtplan-PDF-Export herunter und stößt den Browser-Download an.
 * Nutzt rohes fetch() statt apiClient (siehe api/client.ts) – der
 * openapi-fetch-Client ist nicht für binäre Antworten (PDF) ausgelegt. */
export async function downloadShiftPlanPdf(
  employeeIds: number[],
  dateFrom: string,
  dateTo: string,
): Promise<void> {
  const params = new URLSearchParams({ from: dateFrom, to: dateTo })
  employeeIds.forEach((id) => params.append('employee_ids', String(id)))

  const token = getAccessToken()
  const response = await fetch(`/api/shift-plan/pdf?${params.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? 'PDF-Export fehlgeschlagen.')
  }

  const blob = await response.blob()
  const filename = extractFilename(
    response.headers.get('Content-Disposition'),
    `schichtplan_${dateFrom}_${dateTo}.pdf`,
  )

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
