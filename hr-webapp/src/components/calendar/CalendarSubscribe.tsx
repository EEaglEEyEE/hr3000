import { useState } from 'react'
import { ApiError, apiClient, unwrap } from '../../api/client'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

/** Kalender-Abo (iCal): privater Link für Outlook, Google oder Apple Kalender. */
export function CalendarSubscribe() {
  const [url, setUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const { path } = unwrap(await apiClient.POST('/me/calendar-token', {}))
      setUrl(`${window.location.origin}${path}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.')
    } finally {
      setBusy(false)
    }
  }

  async function stop() {
    setBusy(true)
    await apiClient.DELETE('/me/calendar-token', {})
    setUrl(null)
    setBusy(false)
  }

  if (!url) {
    return (
      <div className="flex flex-col gap-1 text-sm">
        <Button size="sm" variant="outline" className="self-start" disabled={busy} onClick={() => void create()}>
          Kalender abonnieren (iCal)
        </Button>
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-slate-200 p-3 text-sm">
      <span className="font-medium">Abo-Link für Outlook, Google oder Apple Kalender</span>
      <div className="flex gap-2">
        <Input readOnly aria-label="Abo-Link" value={url} onFocus={(e) => e.target.select()} />
        <Button
          size="sm"
          variant="outline"
          onClick={() => void navigator.clipboard?.writeText(url).then(() => setCopied(true))}
        >
          {copied ? 'Kopiert' : 'Kopieren'}
        </Button>
      </div>
      <span className="text-xs text-slate-500">
        Im Kalenderprogramm „Kalender aus dem Internet abonnieren“ wählen und den Link einfügen. Der Link ist privat – wie
        ein Passwort behandeln. Ein neuer Link macht den alten ungültig; er wird nur jetzt angezeigt.
      </span>
      <Button size="sm" variant="ghost" className="self-start" disabled={busy} onClick={() => void stop()}>
        Abo beenden
      </Button>
    </div>
  )
}
