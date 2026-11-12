import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Customer = components['schemas']['CustomerResponse']
export type Project = components['schemas']['ProjectResponse']
export type ProjectCreate = components['schemas']['ProjectCreate']
export type ProjectUpdate = components['schemas']['ProjectUpdate']
export type ProjectTimes = components['schemas']['ProjectTimesResponse']
export type ProjectTimeRow = components['schemas']['ProjectTimeRow']

export function useCustomersQuery(enabled = true) {
  return useQuery({ enabled, queryKey: ['customers'], queryFn: async () => unwrap(await apiClient.GET('/customers')) })
}

export function useProjectsQuery(enabled = true) {
  return useQuery({ enabled, queryKey: ['projects'], queryFn: async () => unwrap(await apiClient.GET('/projects')) })
}

function useInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['customers'] })
    void queryClient.invalidateQueries({ queryKey: ['projects'] })
  }
}

export function useCreateCustomerMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (name: string) => unwrap(await apiClient.POST('/customers', { body: { name, active: true } })),
    onSuccess: invalidate,
  })
}

export function useUpdateCustomerMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: number; name?: string; active?: boolean }) =>
      unwrap(await apiClient.PATCH('/customers/{customer_id}', { params: { path: { customer_id: id } }, body })),
    onSuccess: invalidate,
  })
}

export function useDeleteCustomerMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(await apiClient.DELETE('/customers/{customer_id}', { params: { path: { customer_id: id } } })),
    onSuccess: invalidate,
  })
}

export function useCreateProjectMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (body: ProjectCreate) => unwrap(await apiClient.POST('/projects', { body })),
    onSuccess: invalidate,
  })
}

export function useUpdateProjectMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: ProjectUpdate }) =>
      unwrap(await apiClient.PATCH('/projects/{project_id}', { params: { path: { project_id: id } }, body })),
    onSuccess: invalidate,
  })
}

export function useDeleteProjectMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(await apiClient.DELETE('/projects/{project_id}', { params: { path: { project_id: id } } })),
    onSuccess: invalidate,
  })
}

/** Auswertung „Projektzeiten“ (Analysen). */
export function useProjectTimesQuery(from: string, to: string, enabled = true) {
  return useQuery({
    enabled: enabled && Boolean(from && to),
    queryKey: ['reports', 'project-times', from, to],
    queryFn: async () => unwrap(await apiClient.GET('/reports/project-times', { params: { query: { from, to } } })),
  })
}
