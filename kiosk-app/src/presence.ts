import { useEffect, useRef } from 'react'
import { ApiError, sendHeartbeat, type DeviceLoginResponse, type HeartbeatPayload } from './api'
import { loginWithStoredToken } from './deviceAuth'
import { getQueuedPunches, type QueuedPunch } from './offlineQueue'

/** Abstand im Ruhezustand, falls der Server (noch) keinen nennt */
export const IDLE_HEARTBEAT_SECONDS = 900
const MIN_HEARTBEAT_SECONDS = 5
const MAX_HEARTBEAT_SECONDS = 3600
/** Nach einer gescheiterten Meldung (kein Netz, Serverfehler, abgelaufene Anmeldung) so bald erneut –
 * sonst kostete ein kurzer Aussetzer im Ruhezustand eine Viertelstunde. */
export const HEARTBEAT_RETRY_MS = 60_000

/** Abstand bis zur nächsten Meldung in Millisekunden; unbrauchbare Werte fallen auf den Ruhezustand
 * zurück, alles andere wird auf 5 s bis 1 Std. begrenzt. */
export function heartbeatDelayMs(seconds: number | null | undefined): number {
  const value = typeof seconds === 'number' && Number.isFinite(seconds) ? seconds : IDLE_HEARTBEAT_SECONDS
  return Math.min(MAX_HEARTBEAT_SECONDS, Math.max(MIN_HEARTBEAT_SECONDS, value)) * 1000
}

/** Stand der Offline-Warteschlange für die Meldung. */
export function queueState(queue: QueuedPunch[] = getQueuedPunches()): HeartbeatPayload {
  return { queued_punches: queue.length, failed_punches: queue.filter((punch) => punch.error).length }
}

/** Meldet sich beim Server, solange das Tablet angemeldet ist: sofort (nach der Anmeldung und bei jedem
 * neuen Abstand aus der Konfiguration), danach im Abstand, den der Server nennt – alle 15 Minuten im
 * Ruhezustand, alle 15 Sekunden, solange jemand in der HR-Webapp die Seite „Tablets“ offen hat.
 *
 * Ist die Anmeldung abgelaufen (401), meldet sich das Tablet mit seinem gespeicherten Token neu an –
 * höchstens einmal pro Minute, damit ein abgelehntes Tablet den Server nicht mit Anmeldungen flutet. */
export function usePresenceHeartbeat(
  accessToken: string | undefined,
  seconds: number | undefined,
  onSession: (session: DeviceLoginResponse) => void,
): void {
  const onSessionRef = useRef(onSession)
  useEffect(() => {
    onSessionRef.current = onSession
  }, [onSession])

  useEffect(() => {
    if (!accessToken) return
    const token = accessToken
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    async function beat() {
      let delay = HEARTBEAT_RETRY_MS
      try {
        const response = await sendHeartbeat(token, queueState())
        delay = heartbeatDelayMs(response.interval_seconds)
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          try {
            const refreshed = await loginWithStoredToken()
            // Neue Sitzung: Der Aufrufer setzt sie, dieser Effekt startet damit neu und meldet sich sofort
            if (refreshed && !cancelled) onSessionRef.current(refreshed)
          } catch {
            // Anmeldung abgelehnt oder Server nicht erreichbar – in einer Minute erneut
          }
        }
      }
      if (!cancelled) timer = setTimeout(() => void beat(), delay)
    }

    void beat()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [accessToken, seconds])
}
