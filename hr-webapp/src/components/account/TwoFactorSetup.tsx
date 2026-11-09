import { useEffect, useRef, useState, type FormEvent } from 'react'
import QRCode from 'qrcode'
import type { TwoFactorEnabled, TwoFactorSetup as SetupData } from '../../api/auth'
import { ApiError } from '../../api/client'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

/** Zwei-Faktor-Anmeldung einrichten: QR-Code für die Authenticator-App, Code bestätigen, danach die
 * Wiederherstellungscodes (werden nur jetzt angezeigt). Wird im Konto-Dialog und – wenn die Firma
 * sie vorschreibt – direkt beim Login verwendet. */
export function TwoFactorSetup({
  start,
  enable,
  onDone,
}: {
  start: () => Promise<SetupData>
  enable: (code: string) => Promise<TwoFactorEnabled>
  onDone: (result: TwoFactorEnabled) => void
}) {
  const [setup, setSetup] = useState<SetupData | null>(null)
  const [svg, setSvg] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<TwoFactorEnabled | null>(null)
  const started = useRef(false)

  useEffect(() => {
    // Nur einmal ein Geheimnis erzeugen (jeder Aufruf ersetzt das vorige)
    if (started.current) return
    started.current = true
    start()
      .then(async (data) => {
        setSetup(data)
        setSvg(await QRCode.toString(data.otpauth_uri, { type: 'svg', margin: 1, errorCorrectionLevel: 'M' }))
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.'))
  }, [start])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      setResult(await enable(code.trim()))
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setError('Zu viele Fehlversuche. Bitte warte 15 Minuten.')
      else setError(err instanceof ApiError ? err.message : 'Der Code stimmt nicht.')
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-slate-700">
          Die Zwei-Faktor-Anmeldung ist eingerichtet. Bewahre diese Wiederherstellungscodes sicher auf (z. B. im
          Passwort-Manager). Jeder gilt einmal, falls dein Handy fehlt. Sie werden nur jetzt angezeigt.
        </p>
        <ul className="grid grid-cols-2 gap-1 rounded-md bg-slate-50 p-3 font-mono text-sm" aria-label="Wiederherstellungscodes">
          {result.recovery_codes.map((recovery) => (
            <li key={recovery}>{recovery}</li>
          ))}
        </ul>
        <Button type="button" onClick={() => onDone(result)}>
          Codes gesichert – weiter
        </Button>
      </div>
    )
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
      <p className="text-sm text-slate-600">
        Scanne den QR-Code mit einer Authenticator-App (z. B. Microsoft oder Google Authenticator) und gib den
        angezeigten 6-stelligen Code ein.
      </p>
      <div className="flex justify-center">
        {svg ? (
          // Von der qrcode-Bibliothek erzeugtes SVG (nur Pfade, kein Fremdinhalt)
          <div className="h-48 w-48 rounded-md bg-white p-2" dangerouslySetInnerHTML={{ __html: svg }} />
        ) : (
          <div className="h-48 w-48 animate-pulse rounded-md bg-slate-100" />
        )}
      </div>
      {setup && (
        <p className="text-center text-xs text-slate-500">
          Ohne Kamera diesen Schlüssel in der App eintragen:{' '}
          <span className="font-mono text-slate-700" data-testid="totp-secret">
            {setup.secret.match(/.{1,4}/g)?.join(' ')}
          </span>
        </p>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="totp-setup-code">Code aus der App</Label>
        <Input
          id="totp-setup-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          required
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
        />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Button type="submit" disabled={busy || !setup || code.length !== 6}>
        {busy ? 'Prüfe…' : 'Aktivieren'}
      </Button>
    </form>
  )
}
