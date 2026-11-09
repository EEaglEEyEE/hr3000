import { ApiError, deviceLogin, enrollDevice, type DeviceLoginResponse } from './api'
import { storeDeviceToken, verifyCodeFrom } from './deviceAuth'

/** Registrierungsschlüssel und Gerätename aus der Start-URL, die das MDM setzt. */
export interface EnrollmentParams {
  key: string
  name: string | null
}

/** Liest „#enroll=<schlüssel>&name=<gerätename>“ aus dem Adress-Fragment (geht nie an den Server). */
export function enrollmentFromHash(hash: string): EnrollmentParams | null {
  if (!hash.includes('enroll=')) return null
  let key = ''
  let name: string | null = null
  for (const part of hash.replace(/^#/, '').split('&')) {
    const separator = part.indexOf('=')
    if (separator < 0) continue
    const field = part.slice(0, separator)
    const raw = part.slice(separator + 1)
    if (field === 'enroll') key = raw.trim()
    if (field === 'name') name = deviceNameFrom(raw)
  }
  if (!/^[A-Za-z0-9_-]{20,100}$/.test(key)) return null
  return { key, name }
}

/** Gerätename aus der URL. Nicht ersetzte MDM-Platzhalter zählen als „kein Name“: „%devicename%“
 * (Endpoint Central) muss roh erkannt werden – dekodiert würde „%de“ als Prozent-Kodierung gelesen. */
function deviceNameFrom(raw: string): string | null {
  if (/^%[A-Za-z_]+%$/.test(raw.trim())) return null
  let value: string
  try {
    value = decodeURIComponent(raw.replace(/\+/g, ' '))
  } catch {
    return null
  }
  value = value.trim().slice(0, 100)
  if (!value || /^\{\{.*\}\}$/.test(value)) return null
  return value
}

export type EnrollOutcome =
  | { kind: 'ok'; session: DeviceLoginResponse }
  | { kind: 'pending'; verifyCode: string | null }
  /** retry: vorübergehend (Netz, Server, zu viele Anfragen) – später erneut versuchen */
  | { kind: 'failed'; message: string; retry: boolean }

/** Registriert das Gerät mit dem Schlüssel aus der MDM-Start-URL. Das Token wird sofort gespeichert:
 * Bei PENDING meldet sich das Gerät damit an, sobald Admin/HR es in der HR-Webapp freigegeben haben. */
export async function enrollFromMdm(params: EnrollmentParams): Promise<EnrollOutcome> {
  try {
    const result = await enrollDevice(params.key, params.name)
    storeDeviceToken(result.device_token)
    if (result.status === 'PENDING') return { kind: 'pending', verifyCode: result.verify_code ?? null }
    return { kind: 'ok', session: await deviceLogin(result.device_token) }
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.code === 'DEVICE_PENDING') return { kind: 'pending', verifyCode: verifyCodeFrom(err.message) }
      return { kind: 'failed', message: err.message, retry: err.status === 429 || err.status >= 500 }
    }
    return { kind: 'failed', message: 'Server nicht erreichbar – das Gerät versucht es jede Minute erneut.', retry: true }
  }
}
