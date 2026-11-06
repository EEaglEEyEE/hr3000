import { ApiError, NetworkError, type PunchType } from './api'

export interface QueuedPunch {
  idempotency_key: string
  employee_id: number
  employee_name: string
  punch_type: PunchType
  timestamp_utc: string
  pin?: string
  nfc_uid?: string
  error?: string
}

const QUEUE_KEY = 'kiosk.offline_punch_queue'

function readQueue(): QueuedPunch[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY)
    return raw ? (JSON.parse(raw) as QueuedPunch[]) : []
  } catch {
    return []
  }
}

function writeQueue(queue: QueuedPunch[]): QueuedPunch[] {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
  return queue
}

export function getQueuedPunches(): QueuedPunch[] {
  return readQueue()
}

export function enqueuePunch(punch: QueuedPunch): QueuedPunch[] {
  return writeQueue([...readQueue(), punch])
}

export function discardQueuedPunch(idempotencyKey: string): QueuedPunch[] {
  return writeQueue(readQueue().filter((item) => item.idempotency_key !== idempotencyKey))
}

/** Anmeldung des Tablets gescheitert – sagt nichts über die Stempelung selbst (anders als z. B.
 * PIN_INVALID, das ebenfalls als 401 kommt). NO_SESSION entsteht im Kiosk ohne Anmeldung. */
const DEVICE_AUTH_CODES = new Set(['TOKEN_INVALID', 'INVALID_DEVICE_TOKEN', 'NO_SESSION'])

/** Vorübergehende Störung: kein Netz, Serverfehler (5xx) oder Anmeldung des Tablets abgelehnt
 * (z. B. am 06.11.2026, als Anfragen zeitweise bei der Testumgebung landeten). */
function isTransient(err: unknown): boolean {
  if (err instanceof NetworkError) return true
  if (!(err instanceof ApiError)) return false
  return err.status >= 500 || (err.status === 401 && DEVICE_AUTH_CODES.has(err.code ?? ''))
}

/** Arbeitet die Warteschlange in Reihenfolge ab. Bricht bei einem Netzwerkfehler
 * sofort ab (Rest bleibt für den nächsten Versuch erhalten, Reihenfolge bleibt
 * damit stabil); ein PUNCH_DUPLICATE (409, z.B. weil ein früherer Versuch den
 * Server doch schon erreicht hatte) zählt als Erfolg. Andere Serverfehler (z.B.
 * falscher PIN) markieren den Eintrag nur mit einer Fehlermeldung, damit ein
 * einzelner kaputter Eintrag nicht alle folgenden blockiert. Vorübergehende
 * Störungen zählen wie ein Netzwerkfehler (abbrechen, beim nächsten Versuch
 * erneut), siehe isTransient. */
export async function flushQueue(
  submit: (punch: QueuedPunch) => Promise<unknown>,
  onChange: (queue: QueuedPunch[]) => void,
): Promise<void> {
  for (const punch of readQueue()) {
    if (punch.error) continue
    try {
      await submit(punch)
      onChange(writeQueue(readQueue().filter((item) => item.idempotency_key !== punch.idempotency_key)))
    } catch (err) {
      if (isTransient(err)) return
      if (err instanceof ApiError && err.code === 'PUNCH_DUPLICATE') {
        onChange(writeQueue(readQueue().filter((item) => item.idempotency_key !== punch.idempotency_key)))
        continue
      }
      const message = err instanceof ApiError ? err.message : 'Unbekannter Fehler.'
      onChange(
        writeQueue(
          readQueue().map((item) =>
            item.idempotency_key === punch.idempotency_key ? { ...item, error: message } : item,
          ),
        ),
      )
    }
  }
}
