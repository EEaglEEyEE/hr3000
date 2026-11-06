import { Link } from 'react-router-dom'
import { useMonthlyCapsQuery } from '../../api/queries/timesheets'
import { formatMinutesAsHours } from '../../lib/format'
import { cn } from '../../lib/utils'

const hours = (minutes: number) => formatMinutesAsHours(minutes).replace('+', '')

/** Zu klären → „Monatsgrenzen“: Aushilfen "nach Aufwand", die ihre Monatsgrenze erreichen (≥ 90 %) oder überschreiten. */
export function MonthlyCapsNotice() {
  const capsQuery = useMonthlyCapsQuery()
  const rows = capsQuery.data ?? []
  if (capsQuery.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (rows.length === 0) {
    return <p className="text-sm text-slate-500">Keine Aushilfe „nach Aufwand“ nahe an ihrer Monatsgrenze.</p>
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-slate-500">
        Aushilfen „nach Aufwand“, die im laufenden Monat ihre Monatsgrenze erreichen (ab 90 %) oder überschreiten.
      </p>
      <div className="flex flex-col gap-1.5">
        {rows.map((row) => {
          const share = Math.round((row.actual_minutes / row.cap_minutes) * 100)
          return (
            <div key={row.employee_id} className="flex flex-wrap items-center gap-3 text-sm">
              <Link to={`/employees/${row.employee_id}`} className="w-48 text-sky-700 hover:underline">
                {row.last_name}, {row.first_name}
              </Link>
              <div className="h-2 w-40 overflow-hidden rounded-full bg-slate-200">
                <div
                  className={cn('h-full', row.exceeded ? 'bg-red-500' : 'bg-amber-500')}
                  style={{ width: `${Math.min(share, 100)}%` }}
                />
              </div>
              <span className={row.exceeded ? 'font-semibold text-red-600' : 'text-amber-700'}>
                {hours(row.actual_minutes)} von {hours(row.cap_minutes)} Std. ({share} %)
                {row.exceeded ? ' – überschritten' : ''}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
