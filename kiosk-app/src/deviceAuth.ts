import { ApiError, deviceLogin, type DeviceLoginResponse } from './api'

const STORAGE_KEY = 'kiosk.device_token'

export function getStoredDeviceToken(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function storeDeviceToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token)
}

export function clearStoredDeviceToken(): void {
  localStorage.removeItem(STORAGE_KEY)
}

/** Es gibt bewusst keinen Refresh-Endpoint für Geräte (siehe app/api/auth.py) –
 * der rohe device_token ist ein statisches, langlebiges Geheimnis, daher kann
 * bei jedem 401 (abgelaufenes Access-Token, siehe jwt_device_token_expire_hours)
 * einfach erneut damit eingeloggt werden. */
export async function loginWithStoredToken(): Promise<DeviceLoginResponse | null> {
  const token = getStoredDeviceToken()
  if (!token) return null
  return deviceLogin(token)
}

export type ResumeResult =
  | { kind: 'ok'; session: DeviceLoginResponse }
  /** kein Token gespeichert – Tablet ist nicht eingerichtet */
  | { kind: 'none' }
  /** Per MDM registriert, wartet auf Freigabe in der HR-Webapp (Prüfcode am Bildschirm zeigen) */
  | { kind: 'pending'; verifyCode: string | null }
  /** Server hat das Token abgelehnt (401/403) */
  | { kind: 'rejected' }
  /** Ein anderes Gerät ist mit diesem Zugang gekoppelt (DEVICE_IN_USE) – nicht automatisch erneut versuchen */
  | { kind: 'in_use' }
  /** Server nicht erreichbar oder gestört (Netzwerk, 5xx) */
  | { kind: 'unreachable' }

/** Beim Start bzw. auf dem Einrichtungsbildschirm mit dem gespeicherten Token anmelden.
 *
 * Das Token wird hier bewusst nie gelöscht: Eine Ablehnung kann vorübergehend sein – am 06.11.2026
 * landeten Anfragen zeitweise bei der Testumgebung, die das Token nicht kennt, und Tablets, die in
 * der Zeit neu starteten, waren danach abgekoppelt. Gelöscht wird nur über „Tablet zurücksetzen“
 * (Admin-PIN) oder ersetzt durch eine neue Kopplung. */
export async function resumeSession(): Promise<ResumeResult> {
  const token = getStoredDeviceToken()
  if (!token) return { kind: 'none' }
  try {
    return { kind: 'ok', session: await deviceLogin(token) }
  } catch (err) {
    if (err instanceof ApiError && err.code === 'DEVICE_IN_USE') return { kind: 'in_use' }
    if (err instanceof ApiError && err.code === 'DEVICE_PENDING') return { kind: 'pending', verifyCode: verifyCodeFrom(err.message) }
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return { kind: 'rejected' }
    return { kind: 'unreachable' }
  }
}

/** Prüfcode aus der Meldung „… Prüfcode: K7Q-4XZ“ (DEVICE_PENDING). */
export function verifyCodeFrom(message: string): string | null {
  return /Prüfcode: ([A-Z0-9]{3}-[A-Z0-9]{3})/.exec(message)?.[1] ?? null
}

/** Meldung am Einrichtungsbildschirm. mdm: per MDM verteilt (Registrierungsschlüssel in der Start-URL) –
 * nach einer Ablehnung fragt das Tablet erst nach einem Neustart der Kiosk-App erneut an. */
export function resumeMessage(kind: Exclude<ResumeResult['kind'], 'ok'>, mdm = false): string | undefined {
  if (kind === 'in_use')
    return 'Dieser Tablet-Zugang ist auf einem anderen Gerät gekoppelt. Zum Wechseln in der HR-Webapp unter „Tablets“ den QR-Code öffnen und hier scannen.'
  if (kind === 'rejected' && mdm)
    return 'Der Server hat die Anmeldung dieses Tablets abgelehnt – die Anfrage wurde abgelehnt, das Tablet entfernt oder sein Zugang an ein anderes Gerät vergeben. Zum erneuten Anfragen die Kiosk-App neu starten.'
  if (kind === 'rejected')
    return 'Der Server hat die Anmeldung dieses Tablets abgelehnt. Es versucht es jede Minute erneut – wurde es in der HR-Webapp entfernt, bitte neu einrichten.'
  if (kind === 'unreachable')
    return 'Server nicht erreichbar – das Tablet meldet sich automatisch wieder an, sobald er erreichbar ist.'
  return undefined
}
