import { useEffect, useRef, useState } from 'react'

interface DetectedBarcode {
  rawValue: string
}

interface BarcodeDetectorLike {
  detect: (source: HTMLVideoElement) => Promise<DetectedBarcode[]>
}

type BarcodeDetectorCtor = new (options: { formats: string[] }) => BarcodeDetectorLike

function detectorCtor(): BarcodeDetectorCtor | undefined {
  return (window as Window & { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector
}

/** QR-Scanner über die Kamera (eingebaute BarcodeDetector-API von Chrome/Android, keine
 * Zusatzbibliothek). Liefert den gelesenen Text einmalig an onResult. */
export function isQrScanSupported(): boolean {
  return typeof window !== 'undefined' && !!detectorCtor() && !!navigator.mediaDevices?.getUserMedia
}

export function QrScanner({
  onResult,
  onCancel,
  facingMode = 'environment',
}: {
  onResult: (value: string) => void
  onCancel: () => void
  /** 'user' = Frontkamera (Mitarbeiter halten ihren QR-Code vors Tablet), sonst Rückkamera */
  facingMode?: 'user' | 'environment'
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const Ctor = detectorCtor()
    if (!Ctor) return
    const detector = new Ctor({ formats: ['qr_code'] })
    let stream: MediaStream | null = null
    let timer: number | undefined
    let done = false

    async function start() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode } })
        if (!videoRef.current) return
        videoRef.current.srcObject = stream
        await videoRef.current.play()
        timer = window.setInterval(async () => {
          if (done || !videoRef.current) return
          try {
            const codes = await detector.detect(videoRef.current)
            if (codes.length > 0 && codes[0].rawValue) {
              done = true
              onResult(codes[0].rawValue)
            }
          } catch {
            // einzelnes Bild nicht auswertbar – nächster Versuch
          }
        }, 300)
      } catch {
        setError('Kamera nicht verfügbar oder Zugriff nicht erlaubt.')
      }
    }

    void start()
    return () => {
      done = true
      window.clearInterval(timer)
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [onResult])

  return (
    <div className="flex flex-col items-center gap-3">
      <video ref={videoRef} muted playsInline className="aspect-square w-72 rounded-xl bg-black object-cover" />
      {error ? (
        <p className="text-red-400">{error}</p>
      ) : (
        <p className="text-slate-400">QR-Code aus der HR-Webapp (Tablets → QR-Code) vor die Kamera halten.</p>
      )}
      <button type="button" onClick={onCancel} className="rounded-lg border border-slate-700 px-4 py-2 text-slate-300">
        Abbrechen
      </button>
    </div>
  )
}

/** Kopplungscode bzw. Token aus dem QR-Inhalt: Kiosk-Link oder der reine Wert. */
export function tokenFromQr(value: string): string {
  // ".../#pair=ABCD-EFGH" (einmaliger Kopplungscode, aktuell) oder ".../#token=…" (ältere QR-Codes)
  const match = /[#&](?:token|pair)=([^&]+)/.exec(value)
  return (match ? decodeURIComponent(match[1]) : value).trim()
}

/** QR-Code eines Mitarbeiters („HR3000-CARD:<Chip-UID>“, in der HR-Webapp erzeugt) – gilt am Tablet
 * wie ein vorgehaltener Chip. Liefert die UID oder null. */
export function cardUidFromQr(value: string): string | null {
  const match = /^HR3000-CARD:([0-9A-Fa-f:]{4,40})$/.exec(value.trim())
  return match ? match[1] : null
}
