import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type AttributeSection = components['schemas']['AttributeSectionResponse']
export type AttributeDefinition = components['schemas']['AttributeDefinitionResponse']
export type EmployeeAttributeValue = components['schemas']['EmployeeAttributeValue']
export type EmployeeHistoryEntry = components['schemas']['EmployeeHistoryEntry']
export type FieldType = AttributeDefinition['field_type']

export const FIELD_TYPE_LABELS: Record<FieldType, string> = {
  TEXT: 'Text',
  NUMBER: 'Zahl',
  DATE: 'Datum',
  SELECT: 'Auswahl',
  BOOLEAN: 'Ja/Nein',
  EMPLOYEE: 'Person',
}

export const EMPLOYEE_ACCESS_LABELS: Record<AttributeSection['employee_access'], string> = {
  NONE: 'nur Admin/HR',
  VIEW: 'Mitarbeiter sehen es',
  EDIT: 'Mitarbeiter sehen es und schlagen Änderungen vor',
}

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['attribute-sections'] })
}

export function useAttributeSectionsQuery(includeArchived = false) {
  return useQuery({
    queryKey: ['attribute-sections', includeArchived],
    queryFn: async () =>
      unwrap(await apiClient.GET('/attribute-sections', { params: { query: { include_archived: includeArchived } } })),
  })
}

export function useCreateSectionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: components['schemas']['AttributeSectionRequest']) =>
      unwrap(await apiClient.POST('/attribute-sections', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useUpdateSectionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: components['schemas']['AttributeSectionUpdateRequest'] }) =>
      unwrap(await apiClient.PATCH('/attribute-sections/{section_id}', { params: { path: { section_id: id } }, body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useCreateAttributeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: components['schemas']['AttributeDefinitionRequest']) =>
      unwrap(await apiClient.POST('/attributes', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useUpdateAttributeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: components['schemas']['AttributeDefinitionUpdateRequest'] }) =>
      unwrap(await apiClient.PATCH('/attributes/{attribute_id}', { params: { path: { attribute_id: id } }, body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useEmployeeAttributesQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employee-attributes', employeeId],
    queryFn: async () =>
      unwrap(await apiClient.GET('/employees/{employee_id}/attributes', { params: { path: { employee_id: employeeId } } })),
  })
}

export function usePutAttributeMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ attributeId, value, validFrom }: { attributeId: number; value: string | null; validFrom?: string }) =>
      unwrap(
        await apiClient.PUT('/employees/{employee_id}/attributes/{attribute_id}', {
          params: { path: { employee_id: employeeId, attribute_id: attributeId } },
          body: { value, valid_from: validFrom || null },
        }),
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(['employee-attributes', employeeId], data)
      void queryClient.invalidateQueries({ queryKey: ['employee-history', employeeId] })
    },
  })
}

export function useDeleteAttributeValueMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (valueId: number) =>
      unwrap(
        await apiClient.DELETE('/employees/{employee_id}/attributes/values/{value_id}', {
          params: { path: { employee_id: employeeId, value_id: valueId } },
        }),
      ),
    onSuccess: (data) => queryClient.setQueryData(['employee-attributes', employeeId], data),
  })
}

export function useEmployeeHistoryQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employee-history', employeeId],
    queryFn: async () =>
      unwrap(await apiClient.GET('/employees/{employee_id}/history', { params: { path: { employee_id: employeeId } } })),
  })
}

export function useMyAttributesQuery() {
  return useQuery({
    queryKey: ['my-attributes'],
    queryFn: async () => {
      const [sections, values] = await Promise.all([
        apiClient.GET('/me/attributes').then(unwrap),
        apiClient.GET('/me/attribute-values').then(unwrap),
      ])
      return { sections, values }
    },
  })
}
