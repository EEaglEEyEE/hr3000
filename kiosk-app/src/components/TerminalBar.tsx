import { useEffect, useState } from 'react'
import type { PunchType } from '../api'
import { PUNCH_TYPE_LABELS } from '../labels'

export const TERMINAL_ARM_SECONDS = 10

const ACTIONS: { type: PunchType; className: string }[] = [
  { type: 'COME', className: 'bg-emerald-600' },
  { type: 'GO', className: 'bg-rose-600' },
  { type: 'BREAK_START', className: 'bg-amber-600' },
  { type: 'BREAK_END', className: 'bg-sky-600' },
  { type: 'ERRAND_START', className: 'bg-violet-600' },
  { type: 'ERRAND_END', className: 'bg-violet-700' },
]

export interface TerminalResult {
  ok: boolean
  title: string
  detail?: string
}

/** RFID-Terminalmodus: Aktion wählen, dann Chip vorhalten. Die Aktion bleibt nach jedem
 * Scan aktiv (nächster Mitarbeiter kann direkt scannen) und läuft nach 10 s ohne Scan ab. */
export function TerminalBar({
  armed,
  armedUntil,
  onArm,
  onDisarm,
  result,
  breakButtons = true,
  errandButtons = true,
}: {
  armed: PunchType | null
  armedUntil: number
  onArm: (type: PunchType) => void
  onDisarm: () => void
  result: TerminalResult | null
  breakButtons?: boolean
  errandButtons?: boolean
}) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!armed) return
    const interval = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(interval)
  }, [armed])
  const secondsLeft = armed ? Math.max(0, Math.ceil((armedUntil - now) / 1000)) : 0

  return (
    <div className="flex flex-col gap-3 border-b border-slate-800 px-6 py-4">
      <div className="flex flex-wrap items-center gap-3">
        {ACTIONS.filter(
          (a) =>
            (breakButtons || (a.type !== 'BREAK_START' && a.type !== 'BREAK_END')) &&
            (errandButtons || (a.type !== 'ERRAND_START' && a.type !== 'ERRAND_END')),
        ).map((action) => (
          <button
            key={action.type}
            type="button"
            onClick={() => (armed === action.type ? onDisarm() : onArm(action.type))}
            className={`rounded-xl px-6 py-4 text-xl font-semibold text-white transition ${action.className} ${
              armed && armed !== action.type ? 'opacity-30' : ''
            } ${armed === action.type ? 'ring-4 ring-white' : ''}`}
          >
            {PUNCH_TYPE_LABELS[action.type]}
          </button>
        ))}
        <span className="text-lg text-slate-300">
          {armed
            ? `„${PUNCH_TYPE_LABELS[armed]}“ gewählt – jetzt Chip vorhalten (${secondsLeft} s)`
            : 'Aktion wählen und Chip vorhalten – oder Chip direkt vorhalten bzw. Namen antippen'}
        </span>
      </div>
      {result && (
        <div
          className={`rounded-xl px-5 py-3 text-lg ${result.ok ? 'bg-emerald-900 text-emerald-100' : 'bg-red-900 text-red-100'}`}
        >
          <span className="font-semibold">{result.title}</span>
          {result.detail && <span className="ml-3 text-base opacity-90">{result.detail}</span>}
        </div>
      )}
    </div>
  )
}
