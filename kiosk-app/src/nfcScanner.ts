/** Kapselt die Web-NFC-API (NDEFReader) – funktioniert nur in Chrome auf
 * Android und nur in einem sicheren Kontext (HTTPS oder localhost). Andere
 * Browser/Geräte (iPad, Desktop-Chrome) haben die API schlicht nicht; das
 * wird über isNfcSupported() erkannt, damit die UI den Button ausblenden bzw.
 * einen Hinweis anzeigen kann. */

interface NDEFReadingEvent extends Event {
  serialNumber: string
}

interface NDEFReader extends EventTarget {
  scan(options?: { signal?: AbortSignal }): Promise<void>
  onreading: ((event: NDEFReadingEvent) => void) | null
  onreadingerror: ((event: Event) => void) | null
}

declare global {
  interface Window {
    NDEFReader?: new () => NDEFReader
  }
}

const UNAVAILABLE_KEY = 'kiosk.nfc_unavailable'

export function isNfcSupported(): boolean {
  if (typeof window === 'undefined' || !window.NDEFReader || !window.isSecureContext) return false
  // Chrome kennt die API auch auf Geräten ohne NFC-Chip (z.B. viele Galaxy Tabs) – das zeigt sich
  // erst beim Start. Danach den Button nicht mehr anbieten.
  try {
    return localStorage.getItem(UNAVAILABLE_KEY) !== '1'
  } catch {
    return true
  }
}

/** Verständliche Meldung für Web-NFC-Fehler; merkt sich fehlende NFC-Hardware. */
export function describeNfcError(err: unknown): string {
  const name = err instanceof DOMException || err instanceof Error ? err.name : ''
  if (name === 'NotSupportedError') {
    try {
      localStorage.setItem(UNAVAILABLE_KEY, '1')
    } catch {
      // ohne Speicher wird der Hinweis beim nächsten Versuch erneut angezeigt
    }
    return 'Dieses Tablet hat kein NFC (z. B. viele Galaxy Tabs). Bitte einen USB- oder Bluetooth-RFID-Leser anschließen – er wird automatisch erkannt.'
  }
  if (name === 'NotReadableError') return 'NFC ist ausgeschaltet – bitte in den Android-Einstellungen unter „Verbindungen“ aktivieren.'
  if (name === 'NotAllowedError') return 'NFC-Zugriff wurde nicht erlaubt. Bitte in Chrome für diese Seite erlauben.'
  return err instanceof Error ? err.message : 'NFC konnte nicht gestartet werden.'
}

export function isNfcPresentButInsecureContext(): boolean {
  return typeof window !== 'undefined' && !!window.NDEFReader && !window.isSecureContext
}

export interface NfcScanSession {
  stop: () => void
}

export async function startNfcScan(
  onRead: (serialNumber: string) => void,
  onError: (message: string) => void,
): Promise<NfcScanSession> {
  if (!window.NDEFReader) throw new Error('Web NFC wird von diesem Browser nicht unterstützt.')

  const controller = new AbortController()
  const reader = new window.NDEFReader()
  reader.onreading = (event) => {
    if (event.serialNumber) {
      onRead(event.serialNumber)
    } else {
      onError('Karte hat keine lesbare Seriennummer.')
    }
  }
  reader.onreadingerror = () => {
    onError('Karte konnte nicht gelesen werden.')
  }

  await reader.scan({ signal: controller.signal })

  return { stop: () => controller.abort() }
}
