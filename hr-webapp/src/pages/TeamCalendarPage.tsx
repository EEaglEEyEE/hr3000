import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useLocationsQuery } from '../api/queries/locations'
import { useTeamsQuery } from '../api/queries/teams'
import { useTeamCalendarQuery, type TeamCalendarDay } from '../api/queries/teamCalendar'
import { CalendarSubscribe } from '../components/calendar/CalendarSubscribe'
import { ABSENCE_TYPE_LABELS } from '../lib/labels'
import { useAbsenceTypeMap } from '../api/queries/absenceTypes'
import { absenceColorStyle, dayCellStyle } from '../lib/dayCellStyle'
import { cn } from '../lib/utils'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'

const ALL_LOCATIONS = 'all'

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function monthRange(year: number, month: number) {
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const from = `${year}-${pad(month + 1)}-01`
  const to = `${year}-${pad(month + 1)}-${pad(daysInMonth)}`
  return { daysInMonth, from, to }
}

/** Eigene, bewusst schlanke Zellendarstellung statt lib/dayCellStyle.ts: diese
 * Übersicht kennt nur Urlaub/Krankheit/Feiertag, keine Ist-Zeit-Stati – die
 * dortige Tooltip-Fallback-Logik ("Ist –") würde hier nur verwirren. */
function cellClassName(day: TeamCalendarDay | undefined): string {
  if (!day || day.status === null || day.status === undefined) return 'bg-slate-50'
  if (day.status === 'HOLIDAY') return 'bg-teal-100'
  if (day.status === 'ABSENCE') {
    const variant: Record<string, string> = {
      VACATION: 'bg-violet-100',
      SICK: 'bg-amber-100',
      SPECIAL_LEAVE: 'bg-slate-200',
      WORK_TIME: 'bg-emerald-100',
      PUBLIC_HOLIDAY: 'bg-teal-100',
      CHILD_SICK: 'bg-amber-100',
    }
    return variant[day.absence_type ?? 'SPECIAL_LEAVE'] ?? 'bg-slate-200'
  }
  return 'bg-slate-50'
}

function cellTooltip(day: TeamCalendarDay | undefined): string | undefined {
  if (!day || day.status === null || day.status === undefined) return undefined
  if (day.status === 'HOLIDAY') return 'Feiertag'
  if (day.status === 'ABSENCE') return day.absence_type ? ABSENCE_TYPE_LABELS[day.absence_type] : 'Abwesend'
  return undefined
}

/** own = „Mein Bereich“: nur das eigene Team, ohne Filter (siehe GET /me/team-calendar). */
export function TeamCalendarPage({ own = false }: { own?: boolean }) {
  const absenceTypes = useAbsenceTypeMap()
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())
  const [locationFilter, setLocationFilter] = useState(ALL_LOCATIONS)
  // Leer = alle Teams; sonst die ausgewählten (0 = ohne Team).
  const [selectedTeams, setSelectedTeams] = useState<number[]>([])
  const teamsQuery = useTeamsQuery(!own)

  const locationsQuery = useLocationsQuery(!own)
  const { daysInMonth, from, to } = monthRange(year, month)
  const teamCalendarQuery = useTeamCalendarQuery(
    from,
    to,
    locationFilter === ALL_LOCATIONS ? undefined : Number(locationFilter),
    selectedTeams,
    own,
  )

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
  const dayNumbers = Array.from({ length: daysInMonth }, (_, index) => index + 1)
  const isCurrentMonth = year === today.getFullYear() && month === today.getMonth()
  const todayNumber = isCurrentMonth ? today.getDate() : null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {!own && <h1 className="text-lg font-semibold text-slate-900">Kalender</h1>}
        {!own && <div className="w-56">
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
        </div>}
      </div>
      <CalendarSubscribe />
      <p className="text-sm text-slate-500">
        {own
          ? 'Abwesenheiten in deinem Team – bei manchen Arten nur, dass jemand fehlt.'
          : 'Monatsübersicht über Urlaub, Krankheit und Feiertage aller sichtbaren Mitarbeiter.'}
      </p>

      {!own && (teamsQuery.data?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-500">Teams:</span>
          <button
            type="button"
            onClick={() => setSelectedTeams([])}
            className={`rounded-full border px-3 py-1 ${selectedTeams.length === 0 ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300 bg-white'}`}
          >
            Alle
          </button>
          {[...(teamsQuery.data ?? []).map((t) => ({ id: t.id, name: t.name })), { id: 0, name: 'Ohne Team' }].map((team) => {
            const active = selectedTeams.includes(team.id)
            return (
              <button
                key={team.id}
                type="button"
                onClick={() =>
                  setSelectedTeams((current) => (active ? current.filter((id) => id !== team.id) : [...current, team.id]))
                }
                className={`rounded-full border px-3 py-1 ${active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300 bg-white'}`}
              >
                {team.name}
              </button>
            )
          })}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={goToPreviousMonth}
          aria-label="Vorheriger Monat"
          className="rounded-md border border-slate-200 p-2 hover:bg-slate-50"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="w-40 text-center font-medium capitalize text-slate-900">{monthLabel}</span>
        <button
          type="button"
          onClick={goToNextMonth}
          aria-label="Nächster Monat"
          className="rounded-md border border-slate-200 p-2 hover:bg-slate-50"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        {!isCurrentMonth && (
          <button
            type="button"
            onClick={() => {
              setYear(today.getFullYear())
              setMonth(today.getMonth())
            }}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Heute
          </button>
        )}
      </div>

      {teamCalendarQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {teamCalendarQuery.isError && <p className="text-red-600">Kalender konnte nicht geladen werden.</p>}

      {teamCalendarQuery.data && (
        <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="sticky left-0 z-10 bg-slate-50 px-4 py-2 font-medium">Mitarbeiter</th>
                {dayNumbers.map((day) => (
                  <th
                    key={day}
                    title={day === todayNumber ? 'Heute' : undefined}
                    className={cn(
                      'min-w-8 px-1 py-2 text-center font-medium',
                      day === todayNumber && 'bg-sky-100 font-bold text-sky-900',
                    )}
                  >
                    {day === todayNumber ? (
                      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-sky-600 text-white">
                        {day}
                      </span>
                    ) : (
                      day
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {teamCalendarQuery.data.map((employee) => {
                const dayByDate = new Map(employee.days.map((day) => [day.date, day]))
                return (
                  <tr key={employee.employee_id} className="hover:bg-slate-50">
                    <td className="sticky left-0 z-10 bg-white px-4 py-2 font-medium text-slate-800">
                      {employee.last_name}, {employee.first_name}
                    </td>
                    {dayNumbers.map((dayNumber) => {
                      const isoDate = `${year}-${pad(month + 1)}-${pad(dayNumber)}`
                      const day = dayByDate.get(isoDate)
                      return (
                        <td key={isoDate} className={cn('p-0.5', dayNumber === todayNumber && 'bg-sky-50')}>
                          <div
                            title={
                              [
                                day?.absence_label ?? absenceTypes.get(day?.absence_type_id ?? -1)?.name ?? cellTooltip(day),
                                day?.is_birthday ? `Geburtstag ${employee.first_name} ${employee.last_name}` : null,
                              ]
                                .filter(Boolean)
                                .join(' · ') || undefined
                            }
                            style={dayCellStyle(day, absenceTypes)}
                            className={cn(
                              'flex h-7 w-7 items-center justify-center rounded-md text-sm',
                              dayCellStyle(day, absenceTypes) ? '' : cellClassName(day),
                            )}
                          >
                            {day?.is_birthday ? '🎂' : day?.absence_label?.includes('Std.') ? 'h' : day?.half_day || day?.absence_label ? '½' : null}
                          </div>
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
              {teamCalendarQuery.data.length === 0 && (
                <tr>
                  <td colSpan={daysInMonth + 1} className="px-4 py-6 text-center text-slate-500">
                    Keine sichtbaren Mitarbeiter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap gap-4 text-xs text-slate-600">
        {[...absenceTypes.values()]
          .filter((type) => type.active)
          .map((type) => (
            <span key={type.id} className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded" style={absenceColorStyle(type.color)} /> {type.name}
            </span>
          ))}
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded bg-teal-100" /> Feiertag
        </span>
        <span className="flex items-center gap-1.5">🎂 Geburtstag</span>
      </div>
    </div>
  )
}
