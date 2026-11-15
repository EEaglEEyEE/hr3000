import { nativeInstallationId } from './nativeBridge'

const INSTALLATION_KEY = 'kiosk.installation_id'

/** Dauerhafte ID dieser Tablet-Installation. Der Server bindet den Tablet-Zugang an genau eine
 * Installation – ein anderes Gerät mit demselben Token wird abgewiesen (DEVICE_IN_USE).
 *
 * In der Android-App kommt sie beim ersten Start vom Gerät (fest, auch nach „Daten löschen“): Geht der
 * Speicher verloren, meldet sich das Tablet per Registrierungsschlüssel als dieselbe Installation an und
 * braucht keine neue Freigabe. Eine schon gespeicherte ID bleibt – sonst wäre die Bindung weg. */
export function installationId(): string {
  const existing = localStorage.getItem(INSTALLATION_KEY)
  if (existing) return existing
  const native = nativeInstallationId()
  if (native) {
    localStorage.setItem(INSTALLATION_KEY, native)
    return native
  }
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  const id = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  localStorage.setItem(INSTALLATION_KEY, id)
  return id
}

/** SHA-256 (hex) – Chips vergleicht das Tablet nur gehasht (card_hash in der Mitarbeiterliste). */
export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}
