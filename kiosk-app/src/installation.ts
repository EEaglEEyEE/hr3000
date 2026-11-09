const INSTALLATION_KEY = 'kiosk.installation_id'

/** Zufällige, dauerhafte ID dieser Tablet-Installation. Der Server bindet den Tablet-Zugang an genau
 * eine Installation – ein anderes Gerät mit demselben Token wird abgewiesen (DEVICE_IN_USE). */
export function installationId(): string {
  const existing = localStorage.getItem(INSTALLATION_KEY)
  if (existing) return existing
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
