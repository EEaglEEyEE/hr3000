import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Department = components['schemas']['DepartmentResponse']
export type DepartmentCreateRequest = components['schemas']['DepartmentCreateRequest']
export type DepartmentUpdateRequest = components['schemas']['DepartmentUpdateRequest']
export type DepartmentLeader = components['schemas']['DepartmentLeaderResponse']
export type DepartmentLeaderInput = components['schemas']['DepartmentLeaderInput']
export type OrgChartPerson = components['schemas']['OrgChartPerson']
export type OrgChartDepartment = components['schemas']['OrgChartDepartment']

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['departments'] })
  void queryClient.invalidateQueries({ queryKey: ['org-chart'] })
}

export function useDepartmentsQuery(enabled = true) {
  return useQuery({
    queryKey: ['departments'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/departments')),
  })
}

export function useCreateDepartmentMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: DepartmentCreateRequest) => unwrap(await apiClient.POST('/departments', { body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useUpdateDepartmentMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: DepartmentUpdateRequest }) =>
      unwrap(await apiClient.PATCH('/departments/{department_id}', { params: { path: { department_id: id } }, body: payload })),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useDeleteDepartmentMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const result = await apiClient.DELETE('/departments/{department_id}', { params: { path: { department_id: id } } })
      if (result.error) unwrap(result)
    },
    onSuccess: () => invalidate(queryClient),
  })
}

/** Mehrere Mitarbeiter in eine Abteilung aufnehmen (alles oder nichts) – ändert auch die Mitarbeiter. */
export function useAddDepartmentMembersMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, employeeIds }: { id: number; employeeIds: number[] }) =>
      unwrap(
        await apiClient.POST('/departments/{department_id}/members', {
          params: { path: { department_id: id } },
          body: { employee_ids: employeeIds },
        }),
      ),
    onSuccess: () => {
      invalidate(queryClient)
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
  })
}

export function useOrgChartQuery(enabled = true) {
  return useQuery({
    queryKey: ['org-chart'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/org-chart')),
  })
}

/** Abteilungen als Baum in Anzeige-Reihenfolge, mit Einrückungstiefe (für Listen und Auswahlfelder). */
export function departmentTree(departments: Department[]): { department: Department; depth: number }[] {
  const ids = new Set(departments.map((d) => d.id))
  const children = new Map<number | null, Department[]>()
  for (const department of departments) {
    const parent = department.parent_id !== null && ids.has(department.parent_id) ? department.parent_id : null
    children.set(parent, [...(children.get(parent) ?? []), department])
  }
  const result: { department: Department; depth: number }[] = []
  const visit = (parent: number | null, depth: number) => {
    for (const department of [...(children.get(parent) ?? [])].sort((a, b) => a.name.localeCompare(b.name))) {
      result.push({ department, depth })
      visit(department.id, depth + 1)
    }
  }
  visit(null, 0)
  return result
}
