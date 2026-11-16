/** Schnittstelle zur Android-App „HR3000 Kiosk“ (kiosk-android/, NativeBridge.kt). Im Browser fehlt sie –
 * dann gilt überall das bisherige Verhalten. Die App antwortet nur der konfigurierten Kiosk-Seite. */
export interface HR3000Native {
  installationId(): string
  setKeepAwake(on: boolean): void
  appVersion(): string
  platform(): string
  /** Ab App 1.3.0: Anmeldedaten für die Online-Meldung im Standby (die App meldet sich selbst, solange
   * die Seite eingefroren ist). */
  reportPresence?(deviceToken: string, installationId: string, accessToken: string, queued: number, failed: number): void
  /** Ab App 1.3.0: Tablet zurückgesetzt – keine Meldungen im Standby mehr. */
  clearPresence?(): void
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

export interface NativePresence {
  deviceToken: string
  installationId: string
  accessToken: string
  queued: number
  failed: number
}

/** Nach jeder erfolgreichen Meldung: Die App meldet das Tablet im Standby selbst weiter (sonst warnt der
 * Server nach einer Stunde „offline“). false ohne App oder mit älterer App ohne diese Funktion. */
export function nativeReportPresence(presence: NativePresence): boolean {
  const bridge = nativeBridge()
  if (!bridge || typeof bridge.reportPresence !== 'function') return false
  try {
    bridge.reportPresence(presence.deviceToken, presence.installationId, presence.accessToken, presence.queued, presence.failed)
    return true
  } catch {
    return false
  }
}

/** Tablet zurückgesetzt: Die App vergisst die Anmeldedaten und meldet im Standby nichts mehr. */
export function nativeClearPresence(): boolean {
  const bridge = nativeBridge()
  if (!bridge || typeof bridge.clearPresence !== 'function') return false
  try {
    bridge.clearPresence()
    return true
  } catch {
    return false
  }
}
