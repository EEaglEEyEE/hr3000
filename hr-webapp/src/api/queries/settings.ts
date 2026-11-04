import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Settings = components['schemas']['SettingsResponse']
export type SettingsUpdateRequest = components['schemas']['SettingsUpdateRequest']
export type Bundesland = components['schemas']['Bundesland']

export function useSettingsQuery() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: async () => unwrap(await apiClient.GET('/settings')),
  })
}

export function useUpdateSettingsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Partial<SettingsUpdateRequest>) =>
      unwrap(await apiClient.PATCH('/settings', { body: {
          clear_balance_start_date: false,
          clear_vacation_carry_over_max_days: false,
          clear_core_time: false,
          clear_flex_frame: false,
          clear_kiosk_screen_hours: false,
          ...payload,
        } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
      // Feature-Schalter (z.B. Schichtplanung) steuern Navigation und Reiter.
      void queryClient.invalidateQueries({ queryKey: ['features'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      // Saldo-Beginn/Schichtplanung wirken auf alle Gleitzeitkonten.
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
      void queryClient.invalidateQueries({ queryKey: ['reports'] })
    },
  })
}
