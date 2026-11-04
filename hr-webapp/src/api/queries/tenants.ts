import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Tenant = components['schemas']['TenantResponse']
export type TenantCreateRequest = components['schemas']['TenantCreateRequest']
export type TenantCreateResponse = components['schemas']['TenantCreateResponse']
export type TenantUpdateRequest = components['schemas']['TenantUpdateRequest']
export type TenantAdminPasswordResetResponse = components['schemas']['TenantAdminPasswordResetResponse']
export type TenantAdminEmailUpdateRequest = components['schemas']['TenantAdminEmailUpdateRequest']
export type TenantAdminEmailUpdateResponse = components['schemas']['TenantAdminEmailUpdateResponse']
export type TenantStatus = components['schemas']['TenantStatus']

export function useTenantsQuery() {
  return useQuery({
    queryKey: ['tenants'],
    queryFn: async () => unwrap(await apiClient.GET('/tenants')),
  })
}

export function useCreateTenantMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: TenantCreateRequest) =>
      unwrap(await apiClient.POST('/tenants', { body: payload })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenants'] })
    },
  })
}

// Dient auch zum Ändern des Status (payload = { status: 'ACTIVE'|'TRIAL'|'SUSPENDED' }).
export function useUpdateTenantMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ tenantId, payload }: { tenantId: number; payload: TenantUpdateRequest }) =>
      unwrap(
        await apiClient.PATCH('/tenants/{tenant_id}', {
          params: { path: { tenant_id: tenantId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenants'] })
    },
  })
}

// Kein E-Mail-Versand – das neue Einmalpasswort kommt direkt in der Antwort
// zurück und wird dem Super-Admin einmalig angezeigt (siehe TenantsPage).
export function useResetTenantAdminPasswordMutation() {
  return useMutation({
    mutationFn: async ({ tenantId, sendEmail }: { tenantId: number; sendEmail: boolean }) =>
      unwrap(
        await apiClient.POST('/tenants/{tenant_id}/reset-admin-password', {
          params: { path: { tenant_id: tenantId } },
          body: { send_email: sendEmail },
        }),
      ),
  })
}

export function useUpdateTenantAdminEmailMutation() {
  return useMutation({
    mutationFn: async ({ tenantId, newEmail }: { tenantId: number; newEmail: string }) =>
      unwrap(
        await apiClient.PATCH('/tenants/{tenant_id}/admin-email', {
          params: { path: { tenant_id: tenantId } },
          body: { new_email: newEmail },
        }),
      ),
  })
}

/** Super-Admin: im Namen der Firma kündigen / Kündigung zurücknehmen / sofort endgültig löschen. */
export function useCancelTenantMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ tenantId, revoke }: { tenantId: number; revoke: boolean }) =>
      unwrap(
        revoke
          ? await apiClient.POST('/tenants/{tenant_id}/cancel/revoke', { params: { path: { tenant_id: tenantId } } })
          : await apiClient.POST('/tenants/{tenant_id}/cancel', { params: { path: { tenant_id: tenantId } } }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tenants'] }),
  })
}

export function usePurgeTenantMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ tenantId, confirmSubdomain }: { tenantId: number; confirmSubdomain: string }) =>
      unwrap(
        await apiClient.POST('/tenants/{tenant_id}/purge', {
          params: { path: { tenant_id: tenantId } },
          body: { confirm_subdomain: confirmSubdomain },
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tenants'] }),
  })
}
