import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type SurchargeRule = components['schemas']['SurchargeRuleResponse']
export type SurchargeRuleCreate = components['schemas']['SurchargeRuleCreateRequest']
export type SurchargeReport = components['schemas']['SurchargeReportResponse']

export function useSurchargeRulesQuery() {
  return useQuery({
    queryKey: ['surcharge-rules'],
    queryFn: async () => unwrap(await apiClient.GET('/surcharge-rules')),
  })
}

function useInvalidateRules() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['surcharge-rules'] })
}

export function useCreateSurchargeRuleMutation() {
  const invalidate = useInvalidateRules()
  return useMutation({
    mutationFn: async (payload: SurchargeRuleCreate) => unwrap(await apiClient.POST('/surcharge-rules', { body: payload })),
    onSuccess: invalidate,
  })
}

export function useCreateDefaultSurchargeRulesMutation() {
  const invalidate = useInvalidateRules()
  return useMutation({
    mutationFn: async () => unwrap(await apiClient.POST('/surcharge-rules/defaults')),
    onSuccess: invalidate,
  })
}

export function useToggleSurchargeRuleMutation() {
  const invalidate = useInvalidateRules()
  return useMutation({
    mutationFn: async ({ id, active }: { id: number; active: boolean }) =>
      unwrap(
        await apiClient.PATCH('/surcharge-rules/{rule_id}', {
          params: { path: { rule_id: id } },
          body: { active, clear_exclusive_group: false },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useDeleteSurchargeRuleMutation() {
  const invalidate = useInvalidateRules()
  return useMutation({
    mutationFn: async (id: number) => {
      const result = await apiClient.DELETE('/surcharge-rules/{rule_id}', { params: { path: { rule_id: id } } })
      if (result.error !== undefined) {
        const detail = result.error as { detail?: string; code?: string }
        throw new ApiError(result.response.status, detail.code, detail.detail ?? 'Löschen fehlgeschlagen.')
      }
    },
    onSuccess: invalidate,
  })
}

export function useEmployeeSurchargesQuery(employeeId: number | null, from: string, to: string) {
  return useQuery({
    queryKey: ['employees', employeeId, 'surcharges', from, to],
    enabled: employeeId !== null,
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}/surcharges', {
          params: { path: { employee_id: employeeId as number }, query: { from, to } },
        }),
      ),
  })
}
