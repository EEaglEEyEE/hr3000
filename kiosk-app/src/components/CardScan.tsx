import type { Employee } from '../api'

export type CardScanStatus = 'waiting' | 'saving' | 'done' | 'error'

/** Chip-Registrierung: nach dem PIN den eigenen Chip an den Leser halten. */
export function CardScan({
  employee,
  status,
  message,
  nfcHint,
  onCancel,
}: {
  employee: Employee
  status: CardScanStatus
  message?: string
  nfcHint?: string | null
  onCancel: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 bg-slate-950 p-6 text-center text-white">
      <h1 className="text-3xl font-semibold">
        {employee.first_name} {employee.last_name}
      </h1>
      {status === 'waiting' && (
        <>
          <div className="flex h-40 w-40 animate-pulse items-center justify-center rounded-full border-4 border-emerald-500 text-6xl">
            ⌁
          </div>
          <p className="text-2xl">Jetzt den Chip an den Leser halten</p>
          <p className="text-slate-400">Ein bisher hinterlegter Chip wird ersetzt. Abbruch nach 30 Sekunden.</p>
          {nfcHint && <p className="text-amber-400">{nfcHint}</p>}
        </>
      )}
      {status === 'saving' && <p className="text-2xl text-slate-300">Speichere…</p>}
      {status === 'done' && <p className="text-2xl text-emerald-400">✓ Chip registriert – ab sofort einfach vorhalten.</p>}
      {status === 'error' && <p className="text-xl text-red-400">{message}</p>}
      {status !== 'done' && (
        <button type="button" onClick={onCancel} className="rounded-lg border border-slate-700 px-6 py-3 text-lg text-slate-300">
          {status === 'error' ? 'Zurück' : 'Abbrechen'}
        </button>
      )}
    </div>
  )
}
