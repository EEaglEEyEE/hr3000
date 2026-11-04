import { useAbsenceTypesQuery } from '../../api/queries/absenceTypes'
import { absenceColorStyle, DAY_CELL_LEGEND } from '../../lib/dayCellStyle'
import { cn } from '../../lib/utils'

export function DayCellLegend() {
  const typesQuery = useAbsenceTypesQuery()
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-600">
      {DAY_CELL_LEGEND.map(({ colorClass, label }) => (
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
