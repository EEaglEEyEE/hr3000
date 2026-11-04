import { useEffect, useRef } from 'react'

/** Vereinheitlicht Karten-/Chipnummern wie das Backend (klein, ohne ":", "-", Leerzeichen). */
export function normalizeCardUid(value: string): string {
  return value.trim().toLowerCase().replace(/[:\- ]/g, '')
}

const MAX_KEY_INTERVAL_MS = 60 // USB-/Bluetooth-Leser "tippen" deutlich schneller als ein Mensch
const MIN_UID_LENGTH = 4

/** USB-/Bluetooth-RFID-Leser im Tastatur-Modus: sie senden die Kartennummer als schnelle
 * Tastenfolge mit abschließendem Enter. Funktioniert auf jedem Tablet (auch iPad), anders als
 * Web-NFC, das es nur in Chrome auf Android gibt. */
export function useKeyboardCardReader(onCard: (uid: string) => void, enabled: boolean) {
  const handler = useRef(onCard)
  handler.current = onCard

  useEffect(() => {
    if (!enabled) return
    let buffer = ''
    let lastKeyAt = 0

    function onKeyDown(event: KeyboardEvent) {
      const now = performance.now()
      if (now - lastKeyAt > MAX_KEY_INTERVAL_MS) buffer = ''
      lastKeyAt = now
      if (event.key === 'Enter') {
        if (buffer.length >= MIN_UID_LENGTH) {
          event.preventDefault()
          const uid = buffer
          buffer = ''
          handler.current(uid)
        }
        buffer = ''
        return
      }
      if (event.key.length === 1 && /[0-9a-zA-Z:-]/.test(event.key)) buffer += event.key
    }

    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [enabled])
}
