import { useEffect } from 'react'
import { nativeKeepAwake } from './nativeBridge'

interface WakeLockSentinelLike {
  release: () => Promise<void>
}

/** Hält den Bildschirm des Kiosk-Tablets an (Screen Wake Lock API, Chrome/Android). Der Browser
 * gibt die Sperre beim Wechsel in den Hintergrund frei – beim Zurückkehren wird sie neu angefordert.
 * In der Android-App übernimmt das die App (die eingebettete Ansicht kennt die API nicht sicher). */
export function useWakeLock(active: boolean): void {
  useEffect(() => {
    if (nativeKeepAwake(active)) {
      return () => {
        nativeKeepAwake(false)
      }
    }
    const wakeLock = (navigator as Navigator & { wakeLock?: { request: (type: 'screen') => Promise<WakeLockSentinelLike> } })
      .wakeLock
    if (!active || !wakeLock) return
    let sentinel: WakeLockSentinelLike | null = null
    let cancelled = false

    async function acquire() {
      if (document.visibilityState !== 'visible') return
      try {
        sentinel = await wakeLock!.request('screen')
        if (cancelled) void sentinel.release()
      } catch {
        // z.B. Energiesparmodus – dann bleibt es bei den Geräteeinstellungen
      }
    }

    const onVisibility = () => void acquire()
    void acquire()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisibility)
      void sentinel?.release()
    }
  }, [active])
}
