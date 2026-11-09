import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type ShiftTemplate = components['schemas']['ShiftTemplateResponse']
export type ShiftTemplateCreateRequest = components['schemas']['ShiftTemplateCreateRequest']
export type ShiftTemplateUpdateRequest = components['schemas']['ShiftTemplateUpdateRequest']
export type BreakMode = components['schemas']['BreakMode']
export type TargetPeriod = components['schemas']['TargetPeriod']

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
}

/** Schichtvorlagen des Mandanten (ohne archivierte alte Fassungen). Nur für HR/Führungskräfte. */
export function useShiftTemplatesQuery({ enabled = true } = {}) {
  return useQuery({
    queryKey: ['shift-templates'],
    queryFn: async () => unwrap(await apiClient.GET('/shift-templates')),
    enabled,
  })
}

/** Hat die Vorlage eine eigene Pause (feste Uhrzeit oder feste Minuten)? */
export function templateBreakLabel(template: ShiftTemplate): string {
  if (template.break_mode === 'FIXED' && template.fixed_break_start && template.fixed_break_end) {
    return `${template.fixed_break_start.slice(0, 5)}–${template.fixed_break_end.slice(0, 5)}`
  }
  if (template.min_break_minutes) {
    const after = template.min_break_after_minutes
      ? ` ab ${(template.min_break_after_minutes / 60).toLocaleString('de-DE', { maximumFractionDigits: 2 })} Std.`
      : ''
    return `${template.min_break_minutes} Min.${after}`
  }
  return ''
}

export function useCreateShiftTemplateMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ShiftTemplateCreateRequest) =>
      unwrap(await apiClient.POST('/shift-templates', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useUpdateShiftTemplateMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      templateId,
      payload,
    }: {
      templateId: number
      payload: ShiftTemplateUpdateRequest
    }) =>
      unwrap(
        await apiClient.PATCH('/shift-templates/{template_id}', {
          params: { path: { template_id: templateId } },
          body: payload,
        }),
      ),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useDeleteShiftTemplateMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (templateId: number) => {
      const result = await apiClient.DELETE('/shift-templates/{template_id}', {
        params: { path: { template_id: templateId } },
      })
      if (result.error !== undefined) {
        throw new Error('Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => invalidate(queryClient),
  })
}
