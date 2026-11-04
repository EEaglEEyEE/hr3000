import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useTimesheetQuery, useWeeklyBalanceQuery } from '../../api/queries/timesheets'
import { useAbsenceTypeMap } from '../../api/queries/absenceTypes'
import { dayCellClassName, dayCellStyle, dayCellTooltip } from '../../lib/dayCellStyle'
import { formatMinutesAsHours } from '../../lib/format'
import { cn } from '../../lib/utils'
import { DayCellLegend } from '../shared/DayCellLegend'
import { Button } from '../ui/button'

const WEEKDAY_HEADERS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function toIsoDate(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function monthRange(year: number, month: number) {
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const from = `${year}-${pad(month + 1)}-01`
  const to = `${year}-${pad(month + 1)}-${pad(daysInMonth)}`
  const firstWeekday = new Date(year, month, 1).getDay()
  const leadingOffset = (firstWeekday + 6) % 7 // Woche beginnt Montag
  return { daysInMonth, from, to, leadingOffset }
}

export function CalendarTab({ employeeId }: { employeeId: number }) {
  const absenceTypes = useAbsenceTypeMap()
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())

  const { daysInMonth, from, to, leadingOffset } = monthRange(year, month)
  const timesheetQuery = useTimesheetQuery(employeeId, from, to)
  const weeklyBalanceQuery = useWeeklyBalanceQuery(employeeId, from, to)
  const dayByDate = new Map((timesheetQuery.data ?? []).map((day) => [day.work_date, day]))
  const weekByStart = new Map((weeklyBalanceQuery.data ?? []).map((week) => [week.week_start, week]))

  function goToPreviousMonth() {
    if (month === 0) {
      setYear(year - 1)
      setMonth(11)
    } else {
      setMonth(month - 1)
    }
  }

  function goToNextMonth() {
    if (month === 11) {
      setYear(year + 1)
      setMonth(0)
    } else {
      setMonth(month + 1)
    }
  }

  const monthLabel = new Date(year, month, 1).toLocaleDateString('de-DE', {
    month: 'long',
    year: 'numeric',
  })

  const cells: Array<{ date: string; day: number } | null> = []
  for (let i = 0; i < leadingOffset; i++) cells.push(null)
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push({ date: `${year}-${pad(month + 1)}-${pad(day)}`, day })
  }
  while (cells.length % 7 !== 0) cells.push(null)

  const firstCellDate = new Date(year, month, 1 - leadingOffset)
  const rows: Array<{ cells: typeof cells; weekStart: string }> = []
  for (let i = 0; i < cells.length; i += 7) {
    const weekStartDate = new Date(firstCellDate)
    weekStartDate.setDate(weekStartDate.getDate() + i)
    rows.push({ cells: cells.slice(i, i + 7), weekStart: toIsoDate(weekStartDate) })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="icon" onClick={goToPreviousMonth}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="w-40 text-center font-medium capitalize text-slate-900">{monthLabel}</span>
        <Button variant="outline" size="icon" onClick={goToNextMonth}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {timesheetQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {timesheetQuery.isError && <p className="text-red-600">Kalender konnte nicht geladen werden.</p>}

      <div className="grid grid-cols-[repeat(7,1fr)_7rem] gap-1 text-center text-xs font-medium text-slate-500">
        {WEEKDAY_HEADERS.map((label) => (
          <div key={label}>{label}</div>
        ))}
        <div>Woche</div>
      </div>

      <div className="flex flex-col gap-1">
        {rows.map((row) => {
          const week = weekByStart.get(row.weekStart)
          return (
            <div key={row.weekStart} className="grid grid-cols-[repeat(7,1fr)_7rem] gap-1">
              {row.cells.map((cell, index) => {
                if (!cell) return <div key={`empty-${row.weekStart}-${index}`} />
                const day = dayByDate.get(cell.date)
                return (
                  <div
                    key={cell.date}
                    title={dayCellTooltip(day, absenceTypes)}
                    style={dayCellStyle(day, absenceTypes)}
                    className={cn(
                      'relative flex h-16 flex-col rounded-md p-1.5 text-sm',
                      dayCellClassName(day, absenceTypes),
                    )}
                  >
                    <span className="font-medium">{cell.day}</span>
                    {day?.is_birthday && (
                      <span className="absolute right-1 top-1 text-xs" title="Geburtstag">
                        🎂
                      </span>
                    )}
                    {day?.exceeds_max_daily_minutes && (
                      <span
                        className="absolute left-1 top-1 text-xs"
                        title="Überschreitet die gesetzliche Höchstarbeitszeit von 10 Stunden pro Tag (§3 ArbZG)"
                      >
                        ⚠️
                      </span>
                    )}
                  </div>
                )
              })}
              <div
                className="flex h-16 flex-col justify-center rounded-md bg-slate-50 p-1.5 text-xs text-slate-600"
                title="Soll/Ist/Saldo dieser Kalenderwoche"
              >
                {week ? (
                  <>
                    <span>Soll {formatMinutesAsHours(week.target_minutes)}</span>
                    <span>Ist {formatMinutesAsHours(week.actual_minutes)}</span>
                    <span
                      className={cn(
                        'font-medium',
                        week.delta_minutes === null
                          ? undefined
                          : week.delta_minutes < 0
                            ? 'text-red-600'
                            : week.delta_minutes > 0
                              ? 'text-emerald-600'
                              : undefined,
                      )}
                    >
                      Saldo {formatMinutesAsHours(week.delta_minutes)}
                    </span>
                  </>
                ) : (
                  <span className="text-slate-400">–</span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <DayCellLegend />
    </div>
  )
}
