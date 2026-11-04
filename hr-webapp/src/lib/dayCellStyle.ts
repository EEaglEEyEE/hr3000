import type { CSSProperties } from 'react'
import type { AbsenceTypeDef } from '../api/queries/absenceTypes'
import type { TimesheetDay } from '../api/queries/timesheets'
import { ABSENCE_TYPE_LABELS, DAY_FLAG_LABELS } from './labels'
import { formatMinutesAsHours } from './format'

/** Einheitliche Farbcodierung eines Tages – verwendet in Kalenderansicht und
 * globaler Anwesenheitsübersicht. Das Soll kommt aus der Schichtplanung
 * (siehe app/services/shift_planning_service.py) und wird pro Tag aufgelöst –
 * PLANNED_OFF ist ein expliziter freier Tag laut Plan, zu unterscheiden von
 * einem unkonfigurierten Tag ohne Stempelung (neutral dargestellt). */
export function dayCellClassName(day: TimesheetDay | undefined, types?: Map<number, AbsenceTypeDef>): string {
  if (!day) return 'bg-white'
  // Sonderfall (z.B. außerplanmäßig gestempelt): Farbe des Status + oranger Rahmen "zu klären".
  const flagged = day.flags.length > 0 && !day.reviewed ? ' ring-2 ring-amber-500 ring-inset' : ''
  if (day.status === 'ABSENCE' && absenceTypeOf(day, types)) return 'text-slate-800' + flagged
  return baseClassName(day) + flagged
}

type WithAbsence = { status?: string | null; absence_type_id?: number | null; absence_label?: string | null }

function absenceTypeOf(day: WithAbsence | undefined, types?: Map<number, AbsenceTypeDef>): AbsenceTypeDef | undefined {
  if (!day || day.status !== 'ABSENCE' || day.absence_type_id == null) return undefined
  return types?.get(day.absence_type_id)
}

/** Farbe einer eigenen Abwesenheitsart (Einstellungen → Abwesenheitsarten) als zarte Hintergrundfarbe. */
export function absenceColorStyle(color: string): CSSProperties {
  return { backgroundColor: `${color}33`, boxShadow: `inset 0 -3px 0 ${color}` }
}

export function dayCellStyle(day: WithAbsence | undefined, types?: Map<number, AbsenceTypeDef>): CSSProperties | undefined {
  const type = absenceTypeOf(day, types)
  if (type) return absenceColorStyle(type.color)
  // Halber Abwesenheitstag mit Arbeit: Farbe des Stempelstatus + Strich in der Farbe der Abwesenheit.
  const half = day?.absence_label && day.absence_type_id != null ? types?.get(day.absence_type_id) : undefined
  return half ? { boxShadow: `inset 0 -3px 0 ${half.color}` } : undefined
}

function baseClassName(day: TimesheetDay): string {
  if (day.status === 'ABSENCE') {
    const variant: Record<string, string> = {
      VACATION: 'bg-violet-100 text-violet-800',
      SICK: 'bg-amber-100 text-amber-800',
      SPECIAL_LEAVE: 'bg-slate-200 text-slate-700',
      UNPAID: 'bg-slate-200 text-slate-700',
      TIME_OFF_IN_LIEU: 'bg-sky-100 text-sky-800',
      WORK_TIME: 'bg-emerald-100 text-emerald-800',
      PUBLIC_HOLIDAY: 'bg-teal-100 text-teal-800',
      CHILD_SICK: 'bg-amber-100 text-amber-800',
    }
    return variant[day.absence_type ?? 'SPECIAL_LEAVE'] ?? 'bg-slate-200 text-slate-700'
  }
  if (day.status === 'COMPLETE') return 'bg-emerald-100 text-emerald-800'
  if (day.status === 'PRESENT') return 'bg-sky-100 text-sky-800'
  if (day.status === 'ON_BREAK') return 'bg-orange-100 text-orange-800'
  if (day.status === 'ON_ERRAND') return 'bg-violet-100 text-violet-800'
  if (day.status === 'ERROR') return 'bg-red-100 text-red-800'
  if (day.status === 'HOLIDAY') return 'bg-teal-100 text-teal-800'
  if (day.status === 'PLANNED_OFF') return 'bg-indigo-100 text-indigo-800'
  return 'bg-slate-50 text-slate-400'
}

export function dayCellTooltip(day: TimesheetDay | undefined, types?: Map<number, AbsenceTypeDef>): string | undefined {
  if (!day) return undefined
  const typeName = absenceTypeOf(day, types)?.name ?? baseTooltip(day)
  // Halbe Abwesenheitstage: "½ Urlaub" bzw. "½ Urlaub · Ist +4:00"
  const base = day.absence_label
    ? day.status === 'ABSENCE'
      ? day.absence_label
      : `${day.absence_label} · ${baseTooltip(day)}`
    : typeName
  if (day.flags.length === 0) return base
  const reasons = day.flags.map((f) => DAY_FLAG_LABELS[f] ?? f).join(', ')
  return `${base} – ${day.reviewed ? 'geklärt' : 'zu klären'}: ${reasons}`
}

function baseTooltip(day: TimesheetDay): string {
  if (day.status === 'ABSENCE') {
    return day.absence_type ? ABSENCE_TYPE_LABELS[day.absence_type] : 'Abwesend'
  }
  if (day.status === 'PRESENT') return 'Anwesend (noch nicht ausgestempelt)'
  if (day.status === 'ON_BREAK') return 'Pause (noch nicht zurückgestempelt)'
  if (day.status === 'ON_ERRAND') return 'Dienstgang (zählt als Arbeitszeit)'
  if (day.status === 'ERROR') return 'Fehlerhafte Stempelfolge – bitte korrigieren'
  if (day.status === 'HOLIDAY') return 'Feiertag'
  if (day.status === 'PLANNED_OFF') return 'Frei laut Schichtplan'
  if (day.status === 'OPEN_MISSING_PUNCH' && day.actual_minutes === null) return 'Keine Stempelung'
  return `Ist ${formatMinutesAsHours(day.actual_minutes)}`
}

export const DAY_CELL_LEGEND: Array<{ colorClass: string; label: string }> = [
  { colorClass: 'bg-sky-100', label: 'Anwesend' },
  { colorClass: 'bg-orange-100', label: 'Pause' },
  { colorClass: 'bg-violet-100', label: 'Dienstgang' },
  { colorClass: 'bg-emerald-100', label: 'Vollständig' },
  { colorClass: 'bg-teal-100', label: 'Feiertag' },
  { colorClass: 'bg-indigo-100', label: 'Frei laut Plan' },
  { colorClass: 'bg-red-100', label: 'Fehlerhaft' },
  { colorClass: 'bg-slate-50', label: 'Keine Stempelung' },
  { colorClass: 'bg-white ring-2 ring-amber-500 ring-inset', label: 'Sonderfall – zu klären' },
]
