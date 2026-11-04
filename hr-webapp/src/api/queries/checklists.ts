import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type ChecklistTemplate = components['schemas']['TemplateResponse']
export type TemplateItemInput = components['schemas']['TemplateItemInput']
export type TemplateCreate = components['schemas']['TemplateCreateRequest']
export type EmployeeChecklist = components['schemas']['ChecklistResponse']
export type OpenChecklistItem = components['schemas']['OpenChecklistItem']
export type ChecklistRole = components['schemas']['ChecklistRole']

function useInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['checklists'] })
    void queryClient.invalidateQueries({ queryKey: ['employees'] })
  }
}

function throwIfError(result: { error?: unknown; response: Response }) {
  if (result.error !== undefined) {
    const detail = result.error as { detail?: unknown; code?: string }
    throw new ApiError(result.response.status, detail.code, typeof detail.detail === 'string' ? detail.detail : 'Aktion fehlgeschlagen.')
  }
}

export function useChecklistTemplatesQuery() {
  return useQuery({
    queryKey: ['checklists', 'templates'],
    queryFn: async () => unwrap(await apiClient.GET('/checklist-templates')),
  })
}

export function useCreateTemplateMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (payload: TemplateCreate) => unwrap(await apiClient.POST('/checklist-templates', { body: payload })),
    onSuccess: invalidate,
  })
}

export function useCreateDefaultTemplatesMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async () => unwrap(await apiClient.POST('/checklist-templates/defaults')),
    onSuccess: invalidate,
  })
}

export function useDeleteTemplateMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (id: number) =>
      throwIfError(await apiClient.DELETE('/checklist-templates/{template_id}', { params: { path: { template_id: id } } })),
    onSuccess: invalidate,
  })
}

export function useOpenChecklistItemsQuery() {
  return useQuery({
    queryKey: ['checklists', 'open-items'],
    queryFn: async () => unwrap(await apiClient.GET('/checklists/open-items')),
  })
}

export function useEmployeeChecklistsQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'checklists'],
    queryFn: async () =>
      unwrap(await apiClient.GET('/employees/{employee_id}/checklists', { params: { path: { employee_id: employeeId } } })),
  })
}

export function useStartChecklistMutation(employeeId: number) {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (input: { templateId: number; anchorDate?: string }) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/checklists', {
          params: { path: { employee_id: employeeId } },
          body: { template_id: input.templateId, anchor_date: input.anchorDate || null },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useUpdateChecklistItemMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (input: { checklistId: number; itemId: number; done?: boolean; note?: string }) =>
      unwrap(
        await apiClient.PATCH('/checklists/{checklist_id}/items/{item_id}', {
          params: { path: { checklist_id: input.checklistId, item_id: input.itemId } },
          body: { done: input.done ?? null, note: input.note ?? null },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useDeleteChecklistMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (id: number) =>
      throwIfError(await apiClient.DELETE('/checklists/{checklist_id}', { params: { path: { checklist_id: id } } })),
    onSuccess: invalidate,
  })
}
