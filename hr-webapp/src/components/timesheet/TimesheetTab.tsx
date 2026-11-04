import { useState } from 'react'
import {
  useOvertimeBalanceQuery,
  useTimesheetQuery,
  useWeeklyBalanceQuery,
} from '../../api/queries/timesheets'
import { daysAgoIsoDate, formatDate, formatMinutesAsHours, todayIsoDate } from '../../lib/format'
import { DayStatusBadge } from '../shared/DayStatusBadge'
import { DAY_FLAG_LABELS } from '../../lib/labels'
import { BalanceAdjustmentsCard } from './BalanceAdjustmentsCard'
import { Badge } from '../ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

export function TimesheetTab({ employeeId, canAdjust = false }: { employeeId: number; canAdjust?: boolean }) {
  const [from, setFrom] = useState(() => daysAgoIsoDate(13))
  const [to, setTo] = useState(() => todayIsoDate())

  const balanceQuery = useOvertimeBalanceQuery(employeeId)
  const timesheetQuery = useTimesheetQuery(employeeId, from, to)
  const weeklyBalanceQuery = useWeeklyBalanceQuery(employeeId, from, to)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Aktueller Gleitzeitsaldo</CardTitle>
          </CardHeader>
          <CardContent>
            {balanceQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
            {balanceQuery.data && (
              <div className="flex items-baseline gap-2">
                <span
                  className={
                    balanceQuery.data.running_balance_minutes < 0
                      ? 'text-2xl font-semibold text-red-600'
                      : 'text-2xl font-semibold text-emerald-600'
                  }
                >
                  {formatMinutesAsHours(balanceQuery.data.running_balance_minutes)} Std.
                </span>
                {balanceQuery.data.balance_date && (
                  <span className="text-xs text-slate-500">
                    Stand: {formatDate(balanceQuery.data.balance_date)}
                  </span>
                )}
              </div>
            )}
            {balanceQuery.data && balanceQuery.data.adjustment_minutes !== 0 && (
              <p className="mt-1 text-xs text-slate-500">
                inkl. Korrekturbuchungen {formatMinutesAsHours(balanceQuery.data.adjustment_minutes)} Std.
              </p>
            )}
            <p className="mt-2 text-xs text-slate-400">
              {balanceQuery.data && !balanceQuery.data.balance_start
                ? 'Noch kein Konto: es beginnt mit der ersten Stempelung oder ab dem Stichtag unter Einstellungen → „Gleitzeitkonten führen ab“.'
                : `Konto seit ${balanceQuery.data?.balance_start ? formatDate(balanceQuery.data.balance_start) : '–'}. Zählt jeden Tag mit Soll; der heutige erst nach dem Ausstempeln.`}
            </p>
          </CardContent>
        </Card>

        <BalanceAdjustmentsCard employeeId={employeeId} canEdit={canAdjust} />
      </div>

      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="from">Von</Label>
          <Input id="from" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="to">Bis</Label>
          <Input id="to" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-slate-700">Wochenübersicht (Soll/Ist/Saldo)</h3>
        {weeklyBalanceQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
        {weeklyBalanceQuery.data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Woche</TableHead>
                <TableHead>Soll</TableHead>
                <TableHead>Ist</TableHead>
                <TableHead>Saldo</TableHead>
                <TableHead>Abwesenheitstage</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {weeklyBalanceQuery.data.map((week) => (
                <TableRow key={week.week_start}>
                  <TableCell>
                    {formatDate(week.week_start)} – {formatDate(week.week_end)}
                  </TableCell>
                  <TableCell>{formatMinutesAsHours(week.target_minutes)}</TableCell>
                  <TableCell>{formatMinutesAsHours(week.actual_minutes)}</TableCell>
                  <TableCell
                    className={
                      week.delta_minutes === null
                        ? undefined
                        : week.delta_minutes < 0
                          ? 'font-medium text-red-600'
                          : week.delta_minutes > 0
                            ? 'font-medium text-emerald-600'
                            : undefined
                    }
                  >
                    {formatMinutesAsHours(week.delta_minutes)}
                  </TableCell>
                  <TableCell>{week.absence_days}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-slate-700">Tagesansicht</h3>
        {timesheetQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
        {timesheetQuery.isError && <p className="text-red-600">Zeitraum konnte nicht geladen werden.</p>}
        {timesheetQuery.data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Datum</TableHead>
                <TableHead>Ist</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {timesheetQuery.data.map((day) => (
                <TableRow key={day.work_date}>
                  <TableCell>{formatDate(day.work_date)}</TableCell>
                  <TableCell>{formatMinutesAsHours(day.actual_minutes)}</TableCell>
                  <TableCell>
                    {day.status === 'OPEN_MISSING_PUNCH' && day.actual_minutes === null ? (
                      <Badge>Keine Stempelung</Badge>
                    ) : (
                      <DayStatusBadge status={day.status} absenceType={day.absence_type}
                        absenceTypeId={day.absence_type_id} />
                    )}
                    {day.flags.length > 0 && (
                      <Badge
                        variant={day.reviewed ? 'default' : 'warning'}
                        className="ml-1"
                        title={day.flags.map((f) => DAY_FLAG_LABELS[f] ?? f).join(', ')}
                      >
                        {day.reviewed ? 'geklärt' : 'zu klären'}: {day.flags.map((f) => DAY_FLAG_LABELS[f] ?? f).join(', ')}
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
