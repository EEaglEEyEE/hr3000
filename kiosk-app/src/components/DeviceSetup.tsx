import { useCallback, useState, type FormEvent } from 'react'
import { Brand } from './Brand'
import { isQrScanSupported, QrScanner, tokenFromQr } from './QrScanner'

export function DeviceSetup({
  onSubmit,
  error,
  isSubmitting,
  pending,
}: {
  onSubmit: (deviceToken: string) => void
  error?: string
  isSubmitting: boolean
  /** Per MDM registriert, wartet auf Freigabe in der HR-Webapp */
  pending?: { code: string | null } | null
}) {
  const [deviceToken, setDeviceToken] = useState('')
  const [scanning, setScanning] = useState(false)
  const handleScan = useCallback(
    (value: string) => {
      setScanning(false)
      const token = tokenFromQr(value)
      setDeviceToken(token)
      if (token) onSubmit(token)
    },
    [onSubmit],
  )

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (deviceToken.trim()) onSubmit(deviceToken.trim())
  }

  return (
    <div className="flex h-full flex-col items-center justify-center bg-slate-950 p-6 text-white">
      <form onSubmit={handleSubmit} className="flex w-full max-w-md flex-col gap-4">
        <Brand />
        <h1 className="text-2xl font-semibold">Gerät einrichten</h1>
        {pending && (
          <div role="status" className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4 text-center">
            <p className="text-slate-300">Dieses Gerät wartet auf Freigabe in der HR-Webapp unter „Tablets“.</p>
            {pending.code && (
              <p className="mt-2 font-mono text-4xl font-semibold tracking-widest text-white">{pending.code}</p>
            )}
            <p className="mt-2 text-sm text-slate-400">
              Prüfcode beim Freigeben vergleichen. Danach meldet sich das Gerät innerhalb einer Minute von selbst an.
            </p>
          </div>
        )}
        <p className="text-slate-400">
          Scanne den QR-Code aus der HR-Webapp (Tablets → QR-Code) oder gib den dort angezeigten
          Kopplungscode ein (z. B. K7Q4-9XZ2).
        </p>
        {scanning ? (
          <QrScanner onResult={handleScan} onCancel={() => setScanning(false)} />
        ) : (
          isQrScanSupported() && (
            <button
              type="button"
              onClick={() => setScanning(true)}
              className="rounded-lg border border-emerald-500 px-4 py-3 text-lg font-medium text-emerald-400"
            >
              QR-Code scannen
            </button>
          )
        )}
        <input
          autoFocus
          type="text"
          value={deviceToken}
          onChange={(event) => setDeviceToken(event.target.value)}
          placeholder="Kopplungscode oder Gerätetoken"
          autoCapitalize="characters"
          autoComplete="off"
          className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-3 text-lg text-white outline-none focus:border-emerald-500"
        />
        {error && <p className="text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={isSubmitting || !deviceToken.trim()}
          className="rounded-lg bg-emerald-500 px-4 py-3 text-lg font-medium text-slate-950 disabled:opacity-50"
        >
          {isSubmitting ? 'Verbinde…' : 'Verbinden'}
        </button>
      </form>
    </div>
  )
}
