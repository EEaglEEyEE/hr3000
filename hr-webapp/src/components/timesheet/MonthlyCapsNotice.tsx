import { Link } from 'react-router-dom'
import { useMonthlyCapsQuery } from '../../api/queries/timesheets'
import { formatMinutesAsHours } from '../../lib/format'
import { cn } from '../../lib/utils'

const hours = (minutes: number) => formatMinutesAsHours(minutes).replace('+', '')

/** Zu klären: Aushilfen "nach Aufwand", die ihre Monatsgrenze erreichen (≥ 90 %) oder überschreiten. */
export function MonthlyCapsNotice() {
  const capsQuery = useMonthlyCapsQuery()
  const rows = capsQuery.data ?? []
  if (rows.length === 0) return null
  return (
    <div className="flex flex-col gap-2 rounded-md border border-amber-200 bg-amber-50/50 p-4">
      <p className="text-sm font-medium text-slate-900">Monatsgrenzen (laufender Monat)</p>
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
