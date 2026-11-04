import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type TimesheetDay = components['schemas']['TimesheetDay']
export type OvertimeBalance = components['schemas']['OvertimeBalanceResponse']
export type OpenDay = components['schemas']['OpenDayResponse']
export type WeeklyBalanceWeek = components['schemas']['WeeklyBalanceWeek']

export function useWeeklyBalanceQuery(employeeId: number, from: string, to: string) {
  return useQuery({
    queryKey: ['employees', employeeId, 'weekly-balance', from, to],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/weekly-balance', {
          params: { path: { employee_id: employeeId }, query: { from, to } },
        }),
      ),
  })
}

export function useTimesheetQuery(employeeId: number, from: string, to: string) {
  return useQuery({
    queryKey: ['employees', employeeId, 'timesheet', from, to],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/timesheet', {
          params: { path: { employee_id: employeeId }, query: { from, to } },
        }),
      ),
  })
}

export function useOvertimeBalanceQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'overtime-balance'],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/overtime-balance', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
  })
}

export interface EmployeeTimesheet {
  employeeId: number
  days: TimesheetDay[]
}

/** Holt die Timesheet-Tage mehrerer Mitarbeiter parallel für die globale
 * Anwesenheitsübersicht – es gibt keinen Bulk-Endpoint im Backend, dafür
 * bleibt die Anzahl paralleler Requests bei üblicher Firmengröße klein. */
export function useEmployeesTimesheetQuery(employeeIds: number[], from: string, to: string) {
  return useQuery({
    queryKey: ['timesheet-overview', employeeIds, from, to],
    queryFn: async (): Promise<EmployeeTimesheet[]> =>
      Promise.all(
        employeeIds.map(async (employeeId) => ({
          employeeId,
          days: unwrap(
            await apiClient.GET('/employees/{employee_id}/timesheet', {
              params: { path: { employee_id: employeeId }, query: { from, to } },
            }),
          ),
        })),
      ),
    enabled: employeeIds.length > 0,
  })
}

export function useOpenDaysQuery(filters: { from?: string; to?: string; locationId?: number } = {}) {
  return useQuery({
    queryKey: ['open-days', filters],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/timesheet/open-days', {
          params: { query: { from: filters.from, to: filters.to, location_id: filters.locationId } },
        }),
      ),
  })
}

/** Anzahl der Tage unter "Zu klären" für das Menü – teilt den Cache mit der Seite, aktualisiert minütlich. */
export function useOpenDaysCount(): number {
  const { data } = useQuery({
    queryKey: ['open-days', {}],
    queryFn: async () => unwrap(await apiClient.GET('/timesheet/open-days', { params: { query: {} } })),
    refetchInterval: 60_000,
  })
  return data?.length ?? 0
}

/** Aushilfen "nach Aufwand", die ≥ 90 % ihrer Monatsgrenze erreicht haben. */
export function useMonthlyCapsQuery() {
  return useQuery({
    queryKey: ['monthly-caps'],
    queryFn: async () => unwrap(await apiClient.GET('/timesheet/monthly-caps')),
    refetchInterval: 60_000,
  })
}

/** "Erledigt" zurücknehmen – der Tag erscheint wieder unter "Zu klären". */
export function useUnmarkDayReviewedMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ employeeId, workDate }: { employeeId: number; workDate: string }) => {
      const result = await apiClient.DELETE('/employees/{employee_id}/day-reviews/{work_date}', {
        params: { path: { employee_id: employeeId, work_date: workDate } },
      })
      if (result.error !== undefined) throw new Error('Zurücknehmen fehlgeschlagen.')
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['open-days'] })
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
      void queryClient.invalidateQueries({ queryKey: ['period-closures'] })
    },
  })
}

export function useMarkDayReviewedMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ employeeId, workDate, note }: { employeeId: number; workDate: string; note?: string }) => {
      const result = await apiClient.PUT('/employees/{employee_id}/day-reviews/{work_date}', {
        params: { path: { employee_id: employeeId, work_date: workDate } },
        body: { note: note ?? null },
      })
      if (result.error !== undefined) throw new Error('Markieren fehlgeschlagen.')
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['open-days'] })
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
      void queryClient.invalidateQueries({ queryKey: ['period-closures'] })
    },
  })
}
