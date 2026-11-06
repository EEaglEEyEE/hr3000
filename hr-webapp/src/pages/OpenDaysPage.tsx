import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { usePendingAbsencesQuery } from '../api/queries/absences'
import { useCorrectionRequestsQuery } from '../api/queries/correctionRequests'
import { useLocationsQuery } from '../api/queries/locations'
import {
  useMarkDayReviewedMutation,
  useMonthlyCapsQuery,
  useOpenDaysCount,
  useOpenDaysQuery,
  useUnmarkDayReviewedMutation,
} from '../api/queries/timesheets'
import { useAuth } from '../auth/AuthContext'
import { PendingAbsencesPanel } from '../components/absences/PendingAbsencesPanel'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { Button } from '../components/ui/button'
import { DAY_FLAG_LABELS } from '../lib/labels'
import { formatDate, formatMinutesAsHours } from '../lib/format'
import { DayStatusBadge } from '../components/shared/DayStatusBadge'
import { PendingCorrectionRequests } from '../components/punches/CorrectionRequests'
import { MonthlyCapsNotice } from '../components/timesheet/MonthlyCapsNotice'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

const ALL_LOCATIONS = 'all'

/** Reiter des Posteingangs „Zu klären“ (Adresse /zu-klaeren/:reiter). */
const TABS = [
  { key: 'tage', label: 'Tage' },
  { key: 'korrekturen', label: 'Korrekturanträge', fullHrOnly: true },
  { key: 'urlaubsantraege', label: 'Urlaubsanträge' },
  { key: 'monatsgrenzen', label: 'Monatsgrenzen' },
] as const

/** Posteingang: offene Tage, Korrekturanträge, Urlaubsanträge und Monatsgrenzen an einer Stelle. */
export function OpenDaysPage() {
  const navigate = useNavigate()
  const { reiter } = useParams()
  const { isFullHr } = useAuth()
  const counts: Record<string, number> = {
    tage: useOpenDaysCount(),
    korrekturen: useCorrectionRequestsQuery('PENDING', isFullHr).data?.length ?? 0,
    urlaubsantraege: usePendingAbsencesQuery().data?.length ?? 0,
    monatsgrenzen: useMonthlyCapsQuery().data?.length ?? 0,
  }
  const tabs = TABS.filter((tab) => !('fullHrOnly' in tab) || isFullHr)
  const current = tabs.find((tab) => tab.key === reiter)?.key ?? 'tage'

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Zu klären</h1>
      <Tabs value={current} onValueChange={(value) => navigate(`/zu-klaeren/${value}`, { replace: true })}>
        <TabsList>
          {tabs.map((tab) => (
            <TabsTrigger key={tab.key} value={tab.key}>
              {tab.label}
              {counts[tab.key] > 0 && (
                <span className="ml-1.5 rounded-full bg-red-600 px-1.5 text-xs font-semibold leading-5 text-white">
                  {counts[tab.key]}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="tage">
          <OpenDaysList />
        </TabsContent>
        {isFullHr && (
          <TabsContent value="korrekturen">
            <PendingCorrectionRequests />
          </TabsContent>
        )}
        <TabsContent value="urlaubsantraege">
          <PendingAbsencesPanel />
        </TabsContent>
        <TabsContent value="monatsgrenzen">
          <MonthlyCapsNotice />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function OpenDaysList() {
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
      <div className="flex flex-wrap items-center justify-end gap-2">
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
        zugehöriges „Gehen“ –, einer widersprüchlichen Buchungsfolge, einem Arbeitstag ganz ohne
        Stempelung oder einem Sonderfall (siehe Einstellungen, z.B. außerplanmäßig gestempelt, trotz
        Urlaub/Krankheit, an einem Feiertag, zu spät). Korrigierte Tage verschwinden automatisch. Mit
        „Erledigt“ lässt sich ein Tag auch bewusst so stehen lassen, wie er ist – fehlende Zeiten werden
        dabei nicht ergänzt; ändert sich der Tag später, erscheint er wieder. Dieselben Tage zählen beim
        Monatsabschluss, im Monatsbericht und im Lohn-Export als offen.
      </p>

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
                    isFullHr && <span className="text-slate-400">Korrigieren →</span>
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
