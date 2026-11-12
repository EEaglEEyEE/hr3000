import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { components } from './schema'
import { apiClient, unwrap } from './client'
import { authorizedFetch, saveBlob } from './payrollExport'

export type AccountingMonth = components['schemas']['AccountingMonth']
export type AccountingEmployee = components['schemas']['AccountingEmployee']
export type ReleaseInfo = components['schemas']['ReleaseInfo']

/** Freigegebene Monate (neueste zuerst). */
export function usePayrollReleasesQuery(enabled = true) {
  return useQuery({
    queryKey: ['payroll-accounting', 'releases'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/payroll-accounting/releases', { params: { query: {} } })),
  })
}

/** Monat: freigegeben (Schnappschuss) oder – mit Bearbeiten – aktueller Stand. compare: Vergleich mit
 * dem aktuellen Stand bei freigegebenen Monaten. */
export function usePayrollMonthQuery(month: string | null, compare: boolean) {
  return useQuery({
    queryKey: ['payroll-accounting', 'month', month, compare],
    enabled: month !== null,
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/payroll-accounting/{month}', {
          params: { path: { month: month! }, query: { compare } },
        }),
      ),
  })
}

function useInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['payroll-accounting'] })
    void queryClient.invalidateQueries({ queryKey: ['payroll-export-status'] })
  }
}

export function useReleaseMonthMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async ({ month, confirmOpenClosures }: { month: string; confirmOpenClosures: boolean }) =>
      unwrap(
        await apiClient.POST('/payroll-accounting/{month}/release', {
          params: { path: { month } },
          body: { confirm_open_closures: confirmOpenClosures },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useRevokeReleaseMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (month: string) =>
      unwrap(await apiClient.DELETE('/payroll-accounting/{month}/release', { params: { path: { month } } })),
    onSuccess: invalidate,
  })
}

/** Datei des freigegebenen Monats herunterladen (so, wie sie bei der Freigabe entstand). */
export async function downloadPayrollAccountingFile(month: string, kind: 'csv' | 'datev'): Promise<void> {
  const response = await authorizedFetch(`/api/payroll-accounting/${month}/files/${kind}`, 'Download fehlgeschlagen.')
  saveBlob(await response.blob(), kind === 'csv' ? `lohnbuchhaltung_${month}.csv` : `datev-lodas_${month}.txt`)
}
