import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'

/** Eigenes Passwort ändern – liefert ein neues Token-Paar (alle anderen Sitzungen enden). */
export function useChangePasswordMutation() {
  return useMutation({
    mutationFn: async (payload: { current_password: string; new_password: string }) =>
      unwrap(await apiClient.POST('/auth/change-password', { body: payload })),
  })
}

/** HR3000 für die eigene Firma kündigen (nur Admins) bzw. die Kündigung zurücknehmen. */
export function useCancelAccountMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (confirmSubdomain: string) =>
      unwrap(await apiClient.POST('/account/cancel', { body: { confirm_subdomain: confirmSubdomain } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', 'plan'] }),
  })
}

export function useRevokeCancellationMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrap(await apiClient.POST('/account/cancel/revoke')),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', 'plan'] }),
  })
}
