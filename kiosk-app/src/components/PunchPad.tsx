import type { Employee, LeaveEntitlement, OvertimeBalance, PunchType } from '../api'
import { formatDays, formatMinutesAsHours } from '../format'
import { PUNCH_TYPE_LABELS } from '../labels'

const BUTTONS: Array<{ type: PunchType; color: string }> = [
  { type: 'COME', color: 'bg-emerald-600 hover:bg-emerald-500' },
  { type: 'GO', color: 'bg-red-600 hover:bg-red-500' },
  { type: 'BREAK_START', color: 'bg-amber-600 hover:bg-amber-500' },
  { type: 'BREAK_END', color: 'bg-blue-600 hover:bg-blue-500' },
  { type: 'ERRAND_START', color: 'bg-violet-600 hover:bg-violet-500' },
  { type: 'ERRAND_END', color: 'bg-violet-700 hover:bg-violet-600' },
]

export function PunchPad({
  employee,
  isSubmitting,
  error,
  balance,
  leaveEntitlement,
  identifiedViaCard = false,
  pinConfirmed = false,
  breakButtons = true,
  errandButtons = true,
  onRegisterCard,
  onPunch,
  onCancel,
}: {
  employee: Employee
  isSubmitting: boolean
  error: string | null
  balance: OvertimeBalance | null
  leaveEntitlement: LeaveEntitlement | null
  identifiedViaCard?: boolean
  pinConfirmed?: boolean
  /** Einstellungen → Kiosk: Pausen-Buttons anzeigen */
  breakButtons?: boolean
  errandButtons?: boolean
  /** Eigenen Chip registrieren (nur mit PIN, wenn erlaubt) */
  onRegisterCard?: () => void
  onPunch: (type: PunchType) => void
  onCancel: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 bg-slate-950 p-6 text-white">
      <div className="flex flex-col items-center gap-2">
        <h1 className="text-4xl font-semibold">
          {employee.first_name} {employee.last_name}
        </h1>
        {identifiedViaCard && (
          <span className="text-xs uppercase tracking-wide text-emerald-400">Per Chip erkannt</span>
        )}
        {pinConfirmed && (
          <span className="text-xs uppercase tracking-wide text-emerald-400">PIN bestätigt</span>
        )}
        {(balance || leaveEntitlement) && (
          <div className="flex gap-4 text-sm text-slate-400">
            {balance && <span>Überstundenkonto: {formatMinutesAsHours(balance.running_balance_minutes)} Std.</span>}
            {leaveEntitlement && <span>Resturlaub: {formatDays(leaveEntitlement.remaining_days)} Tage</span>}
          </div>
        )}
      </div>
      <div className="grid w-full max-w-2xl grid-cols-2 gap-6">
        {BUTTONS.filter(
          ({ type }) =>
            (breakButtons || (type !== 'BREAK_START' && type !== 'BREAK_END')) &&
            (errandButtons || (type !== 'ERRAND_START' && type !== 'ERRAND_END')),
        ).map(({ type, color }) => (
          <button
            key={type}
            type="button"
            disabled={isSubmitting}
            onClick={() => onPunch(type)}
            className={`rounded-2xl px-8 py-10 text-3xl font-semibold text-white disabled:opacity-50 ${color}`}
          >
            {PUNCH_TYPE_LABELS[type]}
          </button>
        ))}
      </div>
      {error && <p className="text-red-400">{error}</p>}
      {onRegisterCard && (
        <button
          type="button"
          onClick={onRegisterCard}
          disabled={isSubmitting}
          className="text-sm text-slate-400 underline underline-offset-4"
        >
          Eigenen Chip registrieren
        </button>
      )}
      <button
        type="button"
        onClick={onCancel}
        disabled={isSubmitting}
        className="rounded-lg border border-slate-700 px-6 py-3 text-lg text-slate-300"
      >
        Abbrechen
      </button>
    </div>
  )
}
