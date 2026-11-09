import { useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import {
  useMarkAllNotificationsReadMutation,
  useMarkNotificationReadMutation,
  useNotificationSettingsQuery,
  useNotificationsQuery,
  useUpdateNotificationSettingsMutation,
} from '../../api/queries/notifications'
import { cn } from '../../lib/utils'

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' })
}

/** align="right": Liste öffnet nach links (Glocke am rechten Rand, z.B. Handy-Kopfzeile). */
export function NotificationBell({ align = 'left' }: { align?: 'left' | 'right' }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const notificationsQuery = useNotificationsQuery()
  const markRead = useMarkNotificationReadMutation()
  const markAllRead = useMarkAllNotificationsReadMutation()

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const notifications = notificationsQuery.data ?? []
  const unreadCount = notifications.filter((notification) => notification.read_at === null).length

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        aria-label="Benachrichtigungen"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-medium text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className={`absolute z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-md border border-slate-200 bg-white shadow-lg ${
            align === 'right' ? 'right-0' : ''
          }`}
        >
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <span className="text-sm font-medium text-slate-800">Benachrichtigungen</span>
            {unreadCount > 0 && (
              <button
                type="button"
                className="text-xs text-slate-500 hover:text-slate-900"
                disabled={markAllRead.isPending}
                onClick={() => markAllRead.mutate()}
              >
                Alle als gelesen markieren
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 && (
              <p className="p-3 text-sm text-slate-500">Keine Benachrichtigungen.</p>
            )}
            {notifications.map((notification) => (
              <button
                key={notification.id}
                type="button"
                onClick={() => {
                  if (notification.read_at === null) markRead.mutate(notification.id)
                }}
                className={cn(
                  'block w-full border-b border-slate-50 px-3 py-2 text-left text-sm last:border-0 hover:bg-slate-50',
                  notification.read_at === null && 'bg-sky-50',
                )}
              >
                <p className="text-slate-800">{notification.message}</p>
                <p className="mt-0.5 text-xs text-slate-400">{formatTimestamp(notification.created_at)}</p>
              </button>
            ))}
          </div>
          <NotificationEmailToggle enabled={open} />
        </div>
      )}
    </div>
  )
}

/** „Auch per E-Mail“ – persönliche Einstellung; ob überhaupt gemailt wird, legt die Firma fest. */
function NotificationEmailToggle({ enabled }: { enabled: boolean }) {
  const settingsQuery = useNotificationSettingsQuery(enabled)
  const update = useUpdateNotificationSettingsMutation()
  if (!settingsQuery.data) return null
  return (
    <label className="flex items-center gap-2 border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
      <input
        type="checkbox"
        checked={settingsQuery.data.email}
        disabled={update.isPending}
        onChange={(event) => update.mutate(event.target.checked)}
      />
      Benachrichtigungen auch per E-Mail (wenn die Firma einen Mailversand eingerichtet hat)
    </label>
  )
}
