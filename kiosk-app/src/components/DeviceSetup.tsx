import { useCallback, useState, type FormEvent } from 'react'
import { Brand } from './Brand'
import { isQrScanSupported, QrScanner, tokenFromQr } from './QrScanner'

export function DeviceSetup({
  onSubmit,
  error,
  isSubmitting,
}: {
  onSubmit: (deviceToken: string) => void
  error?: string
  isSubmitting: boolean
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
