import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { Button } from '../ui/button'

/** QR-Code fürs Tablet („QR-Code scannen“): enthält die Chip-UID und gilt dort wie ein Chip. */
export function CardQrCode({ uid, name }: { uid: string; name: string }) {
  const [svg, setSvg] = useState<string | null>(null)
  const content = `HR3000-CARD:${uid}`

  useEffect(() => {
    let cancelled = false
    void QRCode.toString(content, { type: 'svg', margin: 1, errorCorrectionLevel: 'M' }).then((value) => {
      if (!cancelled) setSvg(value)
    })
    return () => {
      cancelled = true
    }
  }, [content])

  function print() {
    if (!svg) return
    const win = window.open('', '_blank')
    if (!win) return
    win.document.title = `QR-Code ${name}`
    const box = win.document.createElement('div')
    box.style.cssText = 'width:60mm;font-family:sans-serif;text-align:center'
    box.innerHTML = svg // von der qrcode-Bibliothek erzeugtes SVG (nur Pfade)
    const label = win.document.createElement('p')
    label.textContent = name
    box.appendChild(label)
    win.document.body.appendChild(box)
    win.print()
  }

  return (
    <div className="mt-2 flex items-start gap-3">
      {svg ? (
        // Von der qrcode-Bibliothek erzeugtes SVG (nur Pfade, kein Fremdinhalt)
        <div aria-label={`QR-Code für ${name}`} className="h-28 w-28 shrink-0 rounded bg-white p-1" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <div className="h-28 w-28 shrink-0 animate-pulse rounded bg-slate-100" />
      )}
      <div className="flex flex-col gap-2 text-xs text-slate-500">
        <span>
          Am Tablet „QR-Code scannen“ antippen und den Code vor die Kamera halten – gilt wie der Chip. Ausdrucken oder aufs
          Handy fotografieren. Wer den Code hat, kann für diese Person stempeln (mit „+ PIN“ zusätzlich absichern).
        </span>
        <Button type="button" size="sm" variant="outline" onClick={print} disabled={!svg}>
          Drucken
        </Button>
      </div>
    </div>
  )
}
