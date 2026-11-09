import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { useCreatePairingCodeMutation, type Device } from '../../api/queries/devices'
import { formatDateTime } from '../../lib/format'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'

/** QR-Code zum Einrichten eines Tablets: Link mit dem einmaligen Kopplungscode im Fragment (#pair=…,
 * wird nie an den Server geschickt). Kamera-App des Tablets öffnet den Kiosk, der den Code einlöst
 * und dabei ein neues, an dieses Tablet gebundenes Token bekommt; alternativ in der Kiosk-App
 * „QR-Code scannen“ oder den Code eintippen. Die Kiosk-Adresse liefert der Server mit dem Code
 * (kiosk.firma.hr3000.de bzw. firma.kiosk.… bei fest eingetragenen Hosts); ohne Adresse (z.B.
 * localhost) wird nur der Code kodiert. Das dauerhafte Token zeigt die Webapp nie. */
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
  // Der QR-Code enthält nur den einmaligen Kopplungscode (15 Min.), nie das dauerhafte Token: Koppeln
  // erzeugt ein neues Token für genau dieses Tablet, ein anderes wird damit abgekoppelt.
  const base = pairingCode?.kiosk_url ?? null
  const content = pairingCode ? (base ? `${base}#pair=${encodeURIComponent(pairingCode.code)}` : pairingCode.code) : ''

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
          ) : pairing.isError ? (
            <div className="flex h-64 w-64 items-center justify-center rounded-md bg-red-50 p-4 text-center text-sm text-red-700">
              Kopplungscode konnte nicht erzeugt werden. Bitte Fenster schließen und erneut öffnen.
            </div>
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
            Jeder Zugang gilt für genau ein Tablet. Wird mit dem Code ein anderes Tablet gekoppelt, ist das bisherige
            abgemeldet.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
