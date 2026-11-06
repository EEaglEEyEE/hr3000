import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type PeriodClosure = components['schemas']['PeriodClosureResponse']
export type PeriodStatus = PeriodClosure['status']
export type PeriodOverviewRow = components['schemas']['PeriodOverviewRow']
export type PeriodBulkResultRow = components['schemas']['PeriodBulkResultRow']

interface PeriodRef {
  employeeId: number
  year: number
  month: number
}

function useInvalidatePeriods() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['period-closures'] })
    void queryClient.invalidateQueries({ queryKey: ['employees'] })
  }
}

function pathOf({ employeeId, year, month }: PeriodRef) {
  return { path: { employee_id: employeeId, year, month } }
}

function failIfError(result: { error?: unknown; response: Response }): void {
  if (result.error !== undefined) {
    const detail = result.error as { detail?: unknown; code?: string }
    const message = typeof detail.detail === 'string' ? detail.detail : 'Aktion fehlgeschlagen.'
    throw new ApiError(result.response.status, detail.code, message)
  }
}

export function useEmployeePeriodClosuresQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'period-closures'],
    queryFn: async () =>
      unwrap(await apiClient.GET('/employees/{employee_id}/period-closures', { params: { path: { employee_id: employeeId } } })),
  })
}

export function usePeriodOverviewQuery(year: number, month: number) {
  return useQuery({
    queryKey: ['period-closures', year, month],
    queryFn: async () => unwrap(await apiClient.GET('/period-closures', { params: { query: { year, month } } })),
  })
}

export function useSubmitPeriodMutation() {
  const invalidate = useInvalidatePeriods()
  return useMutation({
    mutationFn: async (input: PeriodRef & { ignoreOpenDays?: boolean; ignoreOpenRequests?: boolean }) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/period-closures/{year}/{month}/submit', {
          params: pathOf(input),
          body: { ignore_open_days: input.ignoreOpenDays ?? false, ignore_open_requests: input.ignoreOpenRequests ?? false },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useSubmitAllPeriodsMutation() {
  const invalidate = useInvalidatePeriods()
  return useMutation({
    mutationFn: async (input: { year: number; month: number; ignoreOpenDays?: boolean }) =>
      unwrap(
        await apiClient.POST('/period-closures/submit-all', {
          body: { year: input.year, month: input.month, ignore_open_days: input.ignoreOpenDays ?? false, ignore_open_requests: false },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useClosePeriodMutation() {
  const invalidate = useInvalidatePeriods()
  return useMutation({
    mutationFn: async (input: PeriodRef) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/period-closures/{year}/{month}/close', {
          params: pathOf(input),
          body: { without_confirmation: true },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useReopenPeriodMutation() {
  const invalidate = useInvalidatePeriods()
  return useMutation({
    mutationFn: async (input: PeriodRef) => {
      failIfError(
        await apiClient.POST('/employees/{employee_id}/period-closures/{year}/{month}/reopen', { params: pathOf(input) }),
      )
    },
    onSuccess: invalidate,
  })
}

export function useConfirmPeriodMutation() {
  const invalidate = useInvalidatePeriods()
  return useMutation({
    mutationFn: async (input: PeriodRef) =>
      unwrap(await apiClient.POST('/employees/{employee_id}/period-closures/{year}/{month}/confirm', { params: pathOf(input) })),
    onSuccess: invalidate,
  })
}

export function useDisputePeriodMutation() {
  const invalidate = useInvalidatePeriods()
  return useMutation({
    mutationFn: async (input: PeriodRef & { reason: string }) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/period-closures/{year}/{month}/dispute', {
          params: pathOf(input),
          body: { reason: input.reason },
        }),
      ),
    onSuccess: invalidate,
  })
}
