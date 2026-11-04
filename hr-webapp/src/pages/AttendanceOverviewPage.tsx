import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEmployeesQuery } from '../api/queries/employees'
import { useLocationsQuery } from '../api/queries/locations'
import { useEmployeesTimesheetQuery } from '../api/queries/timesheets'
import { useAbsenceTypeMap } from '../api/queries/absenceTypes'
import { dayCellClassName, dayCellStyle, dayCellTooltip } from '../lib/dayCellStyle'
import { cn } from '../lib/utils'
import { DayCellLegend } from '../components/shared/DayCellLegend'
import { Button } from '../components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'

const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const ALL_LOCATIONS = 'all'

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function toIsoDate(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function mondayOf(date: Date): Date {
  const diff = (date.getDay() + 6) % 7
  const monday = new Date(date)
  monday.setDate(date.getDate() - diff)
  return monday
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date)
  result.setDate(result.getDate() + days)
  return result
}

export function AttendanceOverviewPage() {
  const absenceTypes = useAbsenceTypeMap()
  const navigate = useNavigate()
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()))
  const [locationFilter, setLocationFilter] = useState(ALL_LOCATIONS)

  const locationsQuery = useLocationsQuery()
  const employeesQuery = useEmployeesQuery({
    active: true,
    locationId: locationFilter === ALL_LOCATIONS ? undefined : Number(locationFilter),
  })

  const weekDays = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index))
  const todayIso = toIsoDate(new Date())
  const isCurrentWeek = weekDays.some((day) => toIsoDate(day) === todayIso)
  const from = toIsoDate(weekDays[0])
  const to = toIsoDate(weekDays[6])

  const employeeIds = (employeesQuery.data ?? []).map((employee) => employee.id)
  const timesheetQuery = useEmployeesTimesheetQuery(employeeIds, from, to)

  const daysByEmployee = new Map(
    (timesheetQuery.data ?? []).map((entry) => [
      entry.employeeId,
      new Map(entry.days.map((day) => [day.work_date, day])),
    ]),
  )

  const weekLabel = `${weekDays[0].toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })} – ${weekDays[6].toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}`

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Anwesenheitsübersicht</h1>
        <div className="w-56">
          <Select value={locationFilter} onValueChange={setLocationFilter}>
            <SelectTrigger>
              <SelectValue placeholder="Alle Standorte" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_LOCATIONS}>Alle Standorte</SelectItem>
              {(locationsQuery.data ?? []).map((location) => (
                <SelectItem key={location.id} value={String(location.id)}>
                  {location.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button variant="outline" size="icon" aria-label="Vorherige Woche" onClick={() => setWeekStart(addDays(weekStart, -7))}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="w-48 text-center font-medium text-slate-900">{weekLabel}</span>
        <Button variant="outline" size="icon" aria-label="Nächste Woche" onClick={() => setWeekStart(addDays(weekStart, 7))}>
          <ChevronRight className="h-4 w-4" />
        </Button>
        {!isCurrentWeek && (
          <Button variant="outline" size="sm" onClick={() => setWeekStart(mondayOf(new Date()))}>
            Heute
          </Button>
        )}
      </div>

      {(employeesQuery.isLoading || timesheetQuery.isLoading) && <p className="text-slate-500">Lädt…</p>}
      {employeesQuery.isError && <p className="text-red-600">Mitarbeiter konnten nicht geladen werden.</p>}

      {employeesQuery.data && (
        <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="sticky left-0 bg-slate-50 px-4 py-2 font-medium">Mitarbeiter</th>
                {weekDays.map((day, index) => {
                  const isToday = toIsoDate(day) === todayIso
                  return (
                    <th
                      key={day.toISOString()}
                      className={cn('px-2 py-2 text-center font-medium', isToday && 'bg-sky-100 text-sky-900')}
                      title={isToday ? 'Heute' : undefined}
                    >
                      <div>{isToday ? 'Heute' : WEEKDAY_LABELS[index]}</div>
                      <div className={cn('text-xs', isToday ? 'font-semibold text-sky-700' : 'text-slate-400')}>
                        {day.getDate()}.{day.getMonth() + 1}.
                      </div>
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {employeesQuery.data.map((employee) => {
                const days = daysByEmployee.get(employee.id)
                return (
                  <tr key={employee.id} className="hover:bg-slate-50">
                    <td
                      className="sticky left-0 cursor-pointer bg-white px-4 py-2 font-medium text-slate-800 hover:underline"
                      onClick={() => navigate(`/employees/${employee.id}`)}
                    >
                      {employee.last_name}, {employee.first_name}
                    </td>
                    {weekDays.map((weekDay) => {
                      const day = days?.get(toIsoDate(weekDay))
                      return (
                        <td
                          key={weekDay.toISOString()}
                          className={cn('p-1', toIsoDate(weekDay) === todayIso && 'bg-sky-50')}
                        >
                          <div
                            title={dayCellTooltip(day, absenceTypes)}
                            style={dayCellStyle(day, absenceTypes)}
                            className={cn('h-8 rounded-md', dayCellClassName(day, absenceTypes))}
                          />
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
              {employeesQuery.data.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-slate-500">
                    Keine aktiven Mitarbeiter gefunden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <DayCellLegend />
    </div>
  )
}
