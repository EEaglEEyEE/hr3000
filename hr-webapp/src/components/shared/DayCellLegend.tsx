import { useAbsenceTypesQuery } from '../../api/queries/absenceTypes'
import { absenceColorStyle, DAY_CELL_LEGEND, DAY_CELL_LEGEND_WITHOUT_TIME_TRACKING } from '../../lib/dayCellStyle'
import { cn } from '../../lib/utils'

/** timeTracking=false: Legende für einen Mitarbeiter ohne Zeiterfassung (ohne Stempelstatus). */
export function DayCellLegend({ timeTracking = true }: { timeTracking?: boolean }) {
  const typesQuery = useAbsenceTypesQuery()
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-600">
      {(timeTracking ? DAY_CELL_LEGEND : DAY_CELL_LEGEND_WITHOUT_TIME_TRACKING).map(({ colorClass, label }) => (
        <div key={label} className="flex items-center gap-1.5">
          <span className={cn('h-3 w-3 rounded-sm', colorClass)} />
          {label}
        </div>
      ))}
      {(typesQuery.data ?? [])
        .filter((type) => type.active)
        .map((type) => (
          <div key={type.id} className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-sm" style={absenceColorStyle(type.color)} />
            {type.name}
          </div>
        ))}
    </div>
  )
}
