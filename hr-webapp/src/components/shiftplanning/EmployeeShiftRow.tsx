import { useState } from 'react'
import type { Employee } from '../../api/queries/employees'
import {
  useDeleteShiftPlanEntryMutation,
  useEffectiveShiftsQuery,
  useUpsertShiftPlanEntryMutation,
  type EffectiveShiftDay,
} from '../../api/queries/shiftPlanEntries'
import type { ShiftTemplate } from '../../api/queries/shiftTemplates'
import { ApiError } from '../../api/client'
import { readShiftDragPayload, setShiftDragPayload } from '../../lib/shiftDragPayload'
import { cn } from '../../lib/utils'

interface EmployeeShiftRowProps {
  employee: Employee
  weekDates: string[]
  templateById: Map<number, ShiftTemplate>
  readOnly: boolean
  onError: (message: string) => void
}

function dayChipClassName(day: EffectiveShiftDay | undefined): string {
  if (!day) return 'bg-white border-slate-200'
  if (!day.is_workday) return 'bg-indigo-50 border-indigo-200 text-indigo-700'
  if (day.from_entry) return 'bg-sky-100 border-sky-300 text-sky-800'
  if (day.plan_exists) return 'bg-slate-100 border-slate-200 text-slate-700'
  return 'bg-white border-dashed border-slate-200 text-slate-400'
}

export function EmployeeShiftRow({
  employee,
  weekDates,
  templateById,
  readOnly,
  onError,
}: EmployeeShiftRowProps) {
  const from = weekDates[0]
  const to = weekDates[weekDates.length - 1]
  const daysQuery = useEffectiveShiftsQuery(employee.id, from, to)
  const upsertEntry = useUpsertShiftPlanEntryMutation(employee.id)
  const deleteEntry = useDeleteShiftPlanEntryMutation(employee.id)
  const [dragOverDate, setDragOverDate] = useState<string | null>(null)

  const dayByDate = new Map((daysQuery.data ?? []).map((day) => [day.date, day]))

  async function handleDrop(targetDate: string, event: React.DragEvent) {
    event.preventDefault()
    setDragOverDate(null)
    const payload = readShiftDragPayload(event)
    if (!payload) return
    try {
      if (payload.kind === 'template') {
        await upsertEntry.mutateAsync({
          date: targetDate,
          payload: { is_workday: true, shift_template_id: payload.templateId },
        })
      } else if (payload.kind === 'off') {
        await upsertEntry.mutateAsync({ date: targetDate, payload: { is_workday: false } })
      } else if (payload.kind === 'move' && payload.employeeId === employee.id) {
        if (payload.sourceDate === targetDate) return
        await upsertEntry.mutateAsync({
          date: targetDate,
          payload: { is_workday: payload.isWorkday, shift_template_id: payload.templateId ?? undefined },
        })
        await deleteEntry.mutateAsync(payload.sourceDate)
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REST_PERIOD_VIOLATION') {
        onError(
          `${employee.first_name} ${employee.last_name}: Die gesetzliche Mindestruhezeit von 11 Stunden (§5 ArbZG) wird unterschritten.`,
        )
      } else if (err instanceof ApiError && err.code === 'MAX_DAILY_WORKING_TIME_EXCEEDED') {
        onError(
          `${employee.first_name} ${employee.last_name}: Die Schicht überschreitet die gesetzliche Höchstarbeitszeit von 10 Stunden pro Tag (§3 ArbZG).`,
        )
      } else {
        onError(`${employee.first_name} ${employee.last_name}: Speichern fehlgeschlagen.`)
      }
    }
  }

  return (
    <tr>
      <td className="whitespace-nowrap border-b border-slate-100 py-2 pr-4 text-sm font-medium text-slate-800">
        {employee.last_name}, {employee.first_name}
      </td>
      {weekDates.map((isoDate) => {
        const day = dayByDate.get(isoDate)
        const template = day?.shift_template_id ? templateById.get(day.shift_template_id) : undefined
        const draggableChip = !readOnly && day?.from_entry === true

        return (
          <td
            key={isoDate}
            className={cn(
              'border-b border-slate-100 p-1 align-top',
              dragOverDate === isoDate && 'bg-emerald-50',
            )}
            onDragOver={(event) => {
              if (readOnly) return
              event.preventDefault()
              setDragOverDate(isoDate)
            }}
            onDragLeave={() => setDragOverDate((current) => (current === isoDate ? null : current))}
            onDrop={readOnly ? undefined : (event) => handleDrop(isoDate, event)}
          >
            {daysQuery.isLoading ? (
              <div className="h-10" />
            ) : (
              <div
                draggable={draggableChip}
                onDragStart={
                  draggableChip
                    ? (event) =>
                        setShiftDragPayload(event, {
                          kind: 'move',
                          employeeId: employee.id,
                          sourceDate: isoDate,
                          templateId: day?.shift_template_id ?? null,
                          isWorkday: day?.is_workday ?? false,
                        })
                    : undefined
                }
                className={cn(
                  'flex min-h-10 flex-col justify-center rounded-md border px-2 py-1 text-xs',
                  dayChipClassName(day),
                  draggableChip && 'cursor-grab active:cursor-grabbing',
                )}
              >
                {!day || (!day.plan_exists && day.is_workday) ? (
                  <span className="text-slate-400">–</span>
                ) : !day.is_workday ? (
                  <span>Frei</span>
                ) : (
                  <>
                    <span className="font-medium">{template?.name ?? 'Schicht'}</span>
                    {template?.start_time && template.end_time && (
                      <span className="text-slate-500">
                        {template.start_time.slice(0, 5)}–{template.end_time.slice(0, 5)}
                      </span>
                    )}
                  </>
                )}
              </div>
            )}
          </td>
        )
      })}
    </tr>
  )
}
