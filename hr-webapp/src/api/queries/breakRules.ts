import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type BreakRule = components['schemas']['BreakRuleResponse']
export type BreakRuleCreateRequest = components['schemas']['BreakRuleCreateRequest']
export type BreakRuleUpdateRequest = components['schemas']['BreakRuleUpdateRequest']

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['break-rules'] })
  // Pausenstaffel wirkt auf Ist-Zeiten und Salden.
  void queryClient.invalidateQueries({ queryKey: ['employees'] })
  void queryClient.invalidateQueries({ queryKey: ['reports'] })
}

export function useBreakRulesQuery() {
  return useQuery({
    queryKey: ['break-rules'],
    queryFn: async () => unwrap(await apiClient.GET('/break-rules')),
  })
}

export function useCreateBreakRuleMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: BreakRuleCreateRequest) =>
      unwrap(await apiClient.POST('/break-rules', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useUpdateBreakRuleMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ ruleId, payload }: { ruleId: number; payload: BreakRuleUpdateRequest }) =>
      unwrap(
        await apiClient.PATCH('/break-rules/{rule_id}', {
          params: { path: { rule_id: ruleId } },
          body: payload,
        }),
      ),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useDeleteBreakRuleMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ ruleId, validFrom }: { ruleId: number; validFrom?: string }) => {
      const result = await apiClient.DELETE('/break-rules/{rule_id}', {
        params: { path: { rule_id: ruleId }, query: validFrom ? { valid_from: validFrom } : {} },
      })
      if (result.error !== undefined) {
        const detail = result.error as { detail?: unknown; code?: string }
        throw new ApiError(result.response.status, detail.code, typeof detail.detail === 'string' ? detail.detail : 'Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => invalidate(queryClient),
  })
}
