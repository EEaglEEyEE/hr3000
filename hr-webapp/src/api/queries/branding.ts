import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { authFetch, failure } from '../documents'

export interface Branding {
  tenant_name: string | null
  logo_data_url: string | null
}

/** Öffentlich (auch auf der Login-Seite): Mandantenname und optionales Firmenlogo. */
export function useBrandingQuery() {
  return useQuery({
    queryKey: ['branding'],
    staleTime: 10 * 60_000,
    queryFn: async (): Promise<Branding> => {
      const response = await fetch('/api/branding')
      if (!response.ok) return { tenant_name: null, logo_data_url: null }
      return (await response.json()) as Branding
    },
  })
}

export function useUploadLogoMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const response = await authFetch('/api/settings/logo', { method: 'PUT', body: form })
      if (!response.ok) throw await failure(response, 'Upload fehlgeschlagen.')
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['branding'] }),
  })
}

export function useDeleteLogoMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const response = await authFetch('/api/settings/logo', { method: 'DELETE' })
      if (!response.ok) throw await failure(response, 'Entfernen fehlgeschlagen.')
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['branding'] }),
  })
}
