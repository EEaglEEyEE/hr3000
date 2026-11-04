import { useEffect } from 'react'
import type { Employee, OvertimeBalance, PunchType } from '../api'
import { formatMinutesAsHours } from '../format'
import { PUNCH_TYPE_LABELS } from '../labels'

const AUTO_DISMISS_MS = 5000

export function ConfirmationOverlay({
  employee,
  punchType,
  balance,
  offline = false,
  onDismiss,
}: {
  employee: Employee
  punchType: PunchType
  balance: OvertimeBalance | null
  offline?: boolean
  onDismiss: () => void
}) {
  useEffect(() => {
    const timeout = setTimeout(onDismiss, AUTO_DISMISS_MS)
    return () => clearTimeout(timeout)
  }, [onDismiss])

  return (
    <button
      type="button"
      onClick={onDismiss}
      className={`flex h-full w-full flex-col items-center justify-center gap-6 text-white ${offline ? 'bg-slate-800' : 'bg-emerald-950'}`}
    >
      <div className="text-6xl">{offline ? '⏳' : '✓'}</div>
      <h1 className="text-4xl font-semibold">
        {employee.first_name} {employee.last_name}
      </h1>
      <p className="text-2xl">{PUNCH_TYPE_LABELS[punchType]} erfasst</p>
      {offline ? (
        <p className="text-xl text-slate-300">Offline gespeichert – wird automatisch gesendet</p>
      ) : (
        balance && (
          <p className="text-xl text-emerald-200">
            Aktueller Saldo: {formatMinutesAsHours(balance.running_balance_minutes)} Std.
          </p>
        )
      )}
      <p className={`text-sm ${offline ? 'text-slate-400' : 'text-emerald-300'}`}>Zum Fortfahren berühren</p>
    </button>
  )
}
