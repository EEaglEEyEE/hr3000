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

/** Ohne includeWorkTimeModels werden die automatisch erzeugten Vorlagen hinter
 * Arbeitszeitmodellen (Wochenstunden ohne Zeiten) ausgeblendet – sie sind keine
 * Schichten, die man auswählen oder pflegen würde. */
export function useShiftTemplatesQuery({ includeWorkTimeModels = false } = {}) {
  return useQuery({
    queryKey: ['shift-templates'],
    queryFn: async () => unwrap(await apiClient.GET('/shift-templates')),
    select: (templates) =>
      includeWorkTimeModels ? templates : templates.filter((template) => !template.is_work_time_model),
  })
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
