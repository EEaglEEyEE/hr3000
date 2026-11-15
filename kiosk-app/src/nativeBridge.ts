/** Schnittstelle zur Android-App „HR3000 Kiosk“ (kiosk-android/, NativeBridge.kt). Im Browser fehlt sie –
 * dann gilt überall das bisherige Verhalten. Die App antwortet nur der konfigurierten Kiosk-Seite. */
export interface HR3000Native {
  installationId(): string
  setKeepAwake(on: boolean): void
  appVersion(): string
  platform(): string
}

declare global {
  interface Window {
    HR3000Native?: HR3000Native
  }
}

const INSTALLATION_ID = /^[A-Za-z0-9_-]{16,100}$/

export function nativeBridge(): HR3000Native | null {
  if (typeof window === 'undefined') return null
  const bridge = window.HR3000Native
  return bridge && typeof bridge.installationId === 'function' ? bridge : null
}

/** Feste Kennung des Geräts aus der App (überlebt „Daten löschen“), sonst null. */
export function nativeInstallationId(): string | null {
  const bridge = nativeBridge()
  if (!bridge) return null
  try {
    const id = String(bridge.installationId() ?? '').trim()
    return INSTALLATION_ID.test(id) ? id : null
  } catch {
    return null
  }
}

/** Bildschirm über die App anlassen; false, wenn es keine App gibt (dann Screen Wake Lock API). */
export function nativeKeepAwake(on: boolean): boolean {
  const bridge = nativeBridge()
  if (!bridge || typeof bridge.setKeepAwake !== 'function') return false
  try {
    bridge.setKeepAwake(on)
    return true
  } catch {
    return false
  }
}
