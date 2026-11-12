import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Role = components['schemas']['RoleResponse']
export type RoleMeta = components['schemas']['RoleMetaResponse']
export type RoleInput = components['schemas']['RoleCreateRequest']
export type HrUser = components['schemas']['HrUserResponse']
export type HrUserCreate = components['schemas']['HrUserCreateRequest']
export type HrUserUpdate = components['schemas']['HrUserUpdateRequest']

/** Eigene Rollen der Firma (nur Admin). */
export function useRolesQuery(enabled = true) {
  return useQuery({
    queryKey: ['roles'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/roles')),
  })
}

/** Bereiche (Matrix) und Vorlagen wie „Lohnbüro (nur lesen)“. */
export function useRoleMetaQuery(enabled = true) {
  return useQuery({
    queryKey: ['roles', 'meta'],
    enabled,
    staleTime: Infinity,
    queryFn: async () => unwrap(await apiClient.GET('/roles/meta')),
  })
}

export function useSaveRoleMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...body }: RoleInput & { id?: number }) =>
      unwrap(
        id === undefined
          ? await apiClient.POST('/roles', { body })
          : await apiClient.PATCH('/roles/{role_id}', { params: { path: { role_id: id } }, body }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['roles'] }),
  })
}

export function useDeleteRoleMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => unwrap(await apiClient.DELETE('/roles/{role_id}', { params: { path: { role_id: id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['roles'] }),
  })
}

/** Reine Verwaltungskonten (ohne Mitarbeiter), z. B. Steuerberatung. */
export function useHrUsersQuery(enabled = true) {
  return useQuery({
    queryKey: ['hr-users'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/hr-users')),
  })
}

function useInvalidateAccounts() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['hr-users'] })
    void queryClient.invalidateQueries({ queryKey: ['roles'] })
  }
}

export function useCreateHrUserMutation() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: async (body: HrUserCreate) => unwrap(await apiClient.POST('/hr-users', { body })),
    onSuccess: invalidate,
  })
}

export function useUpdateHrUserMutation() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: async ({ id, ...body }: HrUserUpdate & { id: number }) =>
      unwrap(await apiClient.PATCH('/hr-users/{hr_user_id}', { params: { path: { hr_user_id: id } }, body })),
    onSuccess: invalidate,
  })
}

export function useDeleteHrUserMutation() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(await apiClient.DELETE('/hr-users/{hr_user_id}', { params: { path: { hr_user_id: id } } })),
    onSuccess: invalidate,
  })
}
