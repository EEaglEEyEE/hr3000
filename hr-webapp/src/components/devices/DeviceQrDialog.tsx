import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { useCreatePairingCodeMutation, type Device } from '../../api/queries/devices'
import { formatDateTime } from '../../lib/format'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'

/** QR-Code zum Einrichten eines Tablets: Link mit Token im Fragment (#token=…, wird nie an
 * den Server geschickt). Kamera-App des Tablets öffnet den Kiosk direkt eingerichtet;
 * alternativ in der Kiosk-App „QR-Code scannen“. Die Kiosk-Adresse liefert der Server mit dem
 * Kopplungscode (kiosk.firma.hr3000.de bzw. firma.kiosk.… bei fest eingetragenen Hosts);
 * ohne Adresse (z.B. localhost oder Fehler) wird nur das Token kodiert. */
export function DeviceQrDialog({ device, onClose }: { device: Device | undefined; onClose: () => void }) {
  const [svg, setSvg] = useState<string | null>(null)
  const pairing = useCreatePairingCodeMutation()
  const [pairingCode, setPairingCode] = useState<{ code: string; expires_at: string; kiosk_url?: string | null } | null>(
    null,
  )

  // Beim Öffnen einen frischen Kopplungscode erzeugen (für Tablets ohne Kamera/QR-Scan).
  const deviceId = device?.id
  useEffect(() => {
    setPairingCode(null)
    if (deviceId === undefined) return
    pairing.mutate(deviceId, { onSuccess: setPairingCode })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId])
  // QR erst, wenn die Antwort da ist (sonst kurz die falsche Adresse) – bei Fehler nur das Token.
  const ready = pairingCode !== null || pairing.isError
  const base = pairingCode?.kiosk_url ?? null
  const content =
    device && ready ? (base ? `${base}#token=${encodeURIComponent(device.device_token)}` : device.device_token) : ''

  useEffect(() => {
    if (!content) return
    let cancelled = false
    void QRCode.toString(content, { type: 'svg', margin: 1, errorCorrectionLevel: 'M' }).then((value) => {
      if (!cancelled) setSvg(value)
    })
    return () => {
      cancelled = true
      setSvg(null)
    }
  }, [content])

  return (
    <Dialog open={device !== undefined} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tablet einrichten – {device?.name}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col items-center gap-3">
          {svg ? (
            // Von der qrcode-Bibliothek erzeugtes SVG (nur Pfade, kein Fremdinhalt)
            <div className="h-64 w-64 rounded-md bg-white p-2" dangerouslySetInnerHTML={{ __html: svg }} />
          ) : (
            <div className="h-64 w-64 animate-pulse rounded-md bg-slate-100" />
          )}
          <p className="text-center text-sm text-slate-600">
            Mit der Kamera des Tablets scannen – die Tablet-App öffnet sich und ist sofort eingerichtet. Oder in der
            Tablet-App „QR-Code scannen“ wählen.
          </p>
          <div className="flex flex-col items-center gap-1 rounded-md bg-slate-50 px-4 py-3">
            <span className="text-xs text-slate-500">Ohne Kamera: diesen Kopplungscode in der Tablet-App eingeben</span>
            <span className="font-mono text-2xl font-semibold tracking-widest text-slate-900">
              {pairingCode?.code ?? (pairing.isError ? '–' : '····-····')}
            </span>
            {pairingCode && (
              <span className="text-xs text-slate-400">
                gültig bis {formatDateTime(pairingCode.expires_at)}, nur einmal verwendbar
              </span>
            )}
          </div>
          <p className="text-center text-xs text-slate-400">
            Der Code enthält das Geräte-Token: nur am Tablet zeigen, nicht weitergeben.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
