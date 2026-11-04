import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Notification = components['schemas']['NotificationResponse']

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['notifications'] })
}

export function useNotificationsQuery() {
  return useQuery({
    queryKey: ['notifications'],
    queryFn: async () => unwrap(await apiClient.GET('/notifications')),
    // Einfaches Polling statt Push (kein WebSocket-Aufwand für eine Glocke) –
    // 30s ist ausreichend zeitnah für Urlaubsanträge/-entscheidungen.
    refetchInterval: 30000,
  })
}

export function useMarkNotificationReadMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (notificationId: number) =>
      unwrap(
        await apiClient.PATCH('/notifications/{notification_id}/read', {
          params: { path: { notification_id: notificationId } },
        }),
      ),
    onSuccess: () => invalidate(queryClient),
  })
}

export function useMarkAllNotificationsReadMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const result = await apiClient.PATCH('/notifications/read-all', {})
      if (result.error !== undefined) {
        throw new Error('Fehlgeschlagen.')
      }
    },
    onSuccess: () => invalidate(queryClient),
  })
}
