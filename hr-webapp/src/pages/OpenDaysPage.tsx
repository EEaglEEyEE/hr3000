import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLocationsQuery } from '../api/queries/locations'
import { useMarkDayReviewedMutation, useOpenDaysQuery, useUnmarkDayReviewedMutation } from '../api/queries/timesheets'
import { useAuth } from '../auth/AuthContext'
import { Button } from '../components/ui/button'
import { DAY_FLAG_LABELS } from '../lib/labels'
import { formatDate, formatMinutesAsHours } from '../lib/format'
import { DayStatusBadge } from '../components/shared/DayStatusBadge'
import { PendingCorrectionRequests } from '../components/punches/CorrectionRequests'
import { MonthlyCapsNotice } from '../components/timesheet/MonthlyCapsNotice'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

const ALL_LOCATIONS = 'all'

export function OpenDaysPage() {
  const navigate = useNavigate()
  const { isFullHr } = useAuth()
  const markReviewed = useMarkDayReviewedMutation()
  const unmarkReviewed = useUnmarkDayReviewedMutation()
  const [lastDone, setLastDone] = useState<{ employeeId: number; workDate: string; label: string } | null>(null)
  const locationsQuery = useLocationsQuery()
  const [locationFilter, setLocationFilter] = useState(ALL_LOCATIONS)

  const openDaysQuery = useOpenDaysQuery({
    locationId: locationFilter === ALL_LOCATIONS ? undefined : Number(locationFilter),
  })

  const locations = locationsQuery.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Zu klären</h1>
        <div className="w-56">
          <Select value={locationFilter} onValueChange={setLocationFilter}>
            <SelectTrigger>
              <SelectValue placeholder="Alle Standorte" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_LOCATIONS}>Alle Standorte</SelectItem>
              {locations.map((location) => (
                <SelectItem key={location.id} value={String(location.id)}>
                  {location.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <p className="text-sm text-slate-500">
        Tage mit einer offenen (unvollständigen) Stempelung – z.B. ein „Kommen“ ohne
        zugehöriges „Gehen“ –, einer widersprüchlichen Buchungsfolge oder einem Sonderfall:
        außerplanmäßig gestempelt, trotz Urlaub/Krankheit, an einem Feiertag, außerhalb der
        Beschäftigung oder über 10 Stunden. Korrigierte Tage verschwinden automatisch. Mit „Erledigt“
        lässt sich ein Tag auch bewusst so stehen lassen, wie er ist – fehlende Zeiten werden dabei
        nicht ergänzt.
      </p>

      {isFullHr && <PendingCorrectionRequests />}
      <MonthlyCapsNotice />

      {lastDone && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-900">
          <span>{lastDone.label}: als erledigt markiert.</span>
          <Button
            size="sm"
            variant="outline"
            disabled={unmarkReviewed.isPending}
            onClick={() => unmarkReviewed.mutate(lastDone, { onSuccess: () => setLastDone(null) })}
          >
            Rückgängig
          </Button>
        </div>
      )}

      {openDaysQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {openDaysQuery.isError && <p className="text-red-600">Liste konnte nicht geladen werden.</p>}

      {openDaysQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Datum</TableHead>
              <TableHead>Mitarbeiter</TableHead>
              <TableHead>Zeiten</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Grund</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {openDaysQuery.data.map((day) => (
              <TableRow
                key={`${day.employee_id}-${day.work_date}`}
                className="cursor-pointer"
                onClick={() => navigate(`/employees/${day.employee_id}`)}
              >
                <TableCell>{formatDate(day.work_date)}</TableCell>
                <TableCell>
                  {day.last_name}, {day.first_name}
                </TableCell>
                <TableCell className="text-sm">
                  {day.times || <span className="text-slate-400">–</span>}
                  {day.actual_minutes != null && day.actual_minutes > 0 && (
                    <span className="ml-2 text-xs text-slate-500">({formatMinutesAsHours(day.actual_minutes)} Std.)</span>
                  )}
                </TableCell>
                <TableCell>
                  <DayStatusBadge status={day.status} />
                </TableCell>
                <TableCell className="text-sm text-amber-800">
                  {day.flags.map((flag) => DAY_FLAG_LABELS[flag] ?? flag).join(', ') ||
                    (day.status === 'ERROR' ? 'Widersprüchliche Buchungen' : 'Stempelung fehlt')}
                </TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  {isFullHr ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={markReviewed.isPending}
                      onClick={(event) => {
                        event.stopPropagation()
                        // Fehlende/widersprüchliche Stempelung: bewusst bestätigen lassen – der Tag zählt dann so, wie er ist.
                        const incomplete = day.status === 'ERROR' || day.status === 'OPEN_MISSING_PUNCH'
                        if (
                          incomplete &&
                          !window.confirm(
                            `${day.first_name} ${day.last_name}, ${formatDate(day.work_date)}: als erledigt markieren, ohne die Stempelung zu korrigieren? Der Tag zählt dann mit der bisher erfassten Zeit.`,
                          )
                        ) {
                          return
                        }
                        markReviewed.mutate(
                          { employeeId: day.employee_id, workDate: day.work_date },
                          {
                            onSuccess: () =>
                              setLastDone({
                                employeeId: day.employee_id,
                                workDate: day.work_date,
                                label: `${day.first_name} ${day.last_name}, ${formatDate(day.work_date)}`,
                              }),
                          },
                        )
                      }}
                    >
                      Erledigt
                    </Button>
                  ) : (
                    <span className="text-slate-400">Korrigieren →</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {openDaysQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-slate-500">
                  Keine offenen Tage – alles geklärt.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
