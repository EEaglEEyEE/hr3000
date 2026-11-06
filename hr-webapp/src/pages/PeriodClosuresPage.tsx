import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  useClosePeriodMutation,
  useReopenPeriodMutation,
  useSubmitAllPeriodsMutation,
  useSubmitPeriodMutation,
  usePeriodOverviewQuery,
  type PeriodBulkResultRow,
  type PeriodOverviewRow,
} from '../api/queries/periodClosures'
import { useAuth } from '../auth/AuthContext'
import { openPdfInNewTab } from '../api/documents'
import { Printer } from 'lucide-react'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { formatMinutesAsHours, todayIsoDate } from '../lib/format'
import { PERIOD_STATUS_LABELS, PERIOD_STATUS_VARIANT } from '../lib/labels'

function previousMonth(): string {
  const [year, month] = todayIsoDate().split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 2, 1))
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
}

export function PeriodClosuresPage() {
  const { isAdmin } = useAuth()
  const [yearMonth, setYearMonth] = useState(previousMonth)
  const [year, month] = yearMonth.split('-').map(Number)
  const overview = usePeriodOverviewQuery(year, month)
  const submit = useSubmitPeriodMutation()
  const submitAll = useSubmitAllPeriodsMutation()
  const close = useClosePeriodMutation()
  const reopen = useReopenPeriodMutation()
  const [message, setMessage] = useState<string | null>(null)
  const [bulkResults, setBulkResults] = useState<PeriodBulkResultRow[] | null>(null)

  async function run(action: () => Promise<unknown>) {
    setMessage(null)
    try {
      await action()
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Aktion fehlgeschlagen.')
    }
  }

  async function handleSubmit(row: PeriodOverviewRow) {
    setMessage(null)
    try {
      await submit.mutateAsync({ employeeId: row.employee_id, year, month })
    } catch (err) {
      if (err instanceof ApiError && (err.code === 'OPEN_DAYS_PRESENT' || err.code === 'OPEN_REQUESTS_PRESENT')) {
        const hint =
          err.code === 'OPEN_DAYS_PRESENT'
            ? 'Offene Tage werden im Nachweis rot markiert.'
            : 'Die Anträge lassen sich danach erst nach „Zurückziehen“ entscheiden.'
        if (window.confirm(`${err.message}\n\nTrotzdem vorlegen? ${hint}`)) {
          await run(() =>
            submit.mutateAsync({ employeeId: row.employee_id, year, month, ignoreOpenDays: true, ignoreOpenRequests: true }),
          )
        }
      } else {
        setMessage(err instanceof ApiError ? err.message : 'Vorlegen fehlgeschlagen.')
      }
    }
  }

  async function handleSubmitAll() {
    if (!window.confirm('Den Monat für alle Mitarbeiter ohne offene Tage zur Bestätigung vorlegen?')) return
    setMessage(null)
    setBulkResults(null)
    try {
      setBulkResults(await submitAll.mutateAsync({ year, month }))
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Vorlegen fehlgeschlagen.')
    }
  }

  const rows = overview.data ?? []
  const skipped = bulkResults?.filter((result) => !result.submitted) ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-slate-900">Monatsabschluss</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Input type="month" className="w-44" value={yearMonth} onChange={(e) => e.target.value && setYearMonth(e.target.value)} />
          <Button
            variant="outline"
            onClick={() =>
              void run(() => openPdfInNewTab(`/month-reports?year=${year}&month=${month}`))
            }
          >
            <Printer className="h-4 w-4" />
            Alle Berichte drucken
          </Button>
          <Button onClick={() => void handleSubmitAll()} disabled={submitAll.isPending}>
            {submitAll.isPending ? 'Legt vor…' : 'Alle vorlegen'}
          </Button>
        </div>
      </div>
      <p className="text-sm text-slate-500">
        Pro Mitarbeiter wird ein Monatsnachweis (PDF) erzeugt und in der Personalakte abgelegt. Der Mitarbeiter bestätigt
        ihn – damit ist der Monat abgeschlossen – oder widerspricht. Ohne Login wird direkt abgeschlossen. Ab dem Vorlegen
        ist der Monat für Stempelungen, Abwesenheiten und Schichtplanung gesperrt; ein Widerspruch oder „Zurückziehen“ öffnet
        ihn wieder. Offene Anträge im Monat werden vor dem Vorlegen gemeldet.
      </p>
      {message && <p className="text-sm text-red-600">{message}</p>}
      {skipped.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-medium">
            {bulkResults!.length - skipped.length} vorgelegt, {skipped.length} übersprungen:
          </p>
          <ul className="list-disc pl-5">
            {skipped.map((result) => (
              <li key={result.employee_id}>
                {result.last_name}, {result.first_name}: {result.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {bulkResults && skipped.length === 0 && (
        <p className="text-sm text-emerald-700">{bulkResults.length} Monatsnachweise vorgelegt.</p>
      )}
      {overview.isLoading && <p className="text-slate-500">Lädt…</p>}
      {overview.isError && <p className="text-red-600">Übersicht konnte nicht geladen werden.</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mitarbeiter</TableHead>
            <TableHead>Nr.</TableHead>
            <TableHead>Offene Tage</TableHead>
            <TableHead>Saldo Monat</TableHead>
            <TableHead>Status</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.employee_id}>
              <TableCell>
                <Link className="text-sky-700 hover:underline" to={`/employees/${row.employee_id}`}>
                  {row.last_name}, {row.first_name}
                </Link>
              </TableCell>
              <TableCell>{row.employee_number}</TableCell>
              <TableCell>
                {row.open_day_count > 0 ? <Badge variant="danger">{row.open_day_count}</Badge> : <span className="text-slate-400">0</span>}
              </TableCell>
              <TableCell>{formatMinutesAsHours(row.delta_minutes)}</TableCell>
              <TableCell>
                {row.status ? (
                  <div className="flex flex-col gap-1">
                    <Badge variant={PERIOD_STATUS_VARIANT[row.status]}>{PERIOD_STATUS_LABELS[row.status]}</Badge>
                    {row.status === 'DISPUTED' && row.dispute_reason && (
                      <span className="max-w-xs text-xs text-red-700">„{row.dispute_reason}“</span>
                    )}
                  </div>
                ) : (
                  <span className="text-slate-400">Offen</span>
                )}
              </TableCell>
              <TableCell className="whitespace-nowrap text-right">
                <Button
                  size="sm"
                  variant="ghost"
                  title="Monatsbericht (Druckansicht)"
                  onClick={() => void run(() => openPdfInNewTab(`/employees/${row.employee_id}/month-report?year=${year}&month=${month}`))}
                >
                  <Printer className="h-4 w-4" />
                </Button>{' '}
                {(row.status === null || row.status === 'DISPUTED') && (
                  <Button size="sm" variant="outline" onClick={() => void handleSubmit(row)}>
                    {row.status === 'DISPUTED' ? 'Neu vorlegen' : 'Vorlegen'}
                  </Button>
                )}
                {row.status === 'SUBMITTED' && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        if (window.confirm('Abschluss ohne Bestätigung des Mitarbeiters? Das wird im Audit-Log vermerkt.')) {
                          void run(() => close.mutateAsync({ employeeId: row.employee_id, year, month }))
                        }
                      }}
                    >
                      Ohne Bestätigung abschließen
                    </Button>{' '}
                    <Button size="sm" variant="ghost" onClick={() => void run(() => reopen.mutateAsync({ employeeId: row.employee_id, year, month }))}>
                      Zurückziehen
                    </Button>
                  </>
                )}
                {row.status === 'CLOSED' && isAdmin && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (window.confirm('Monat wieder öffnen? Der bisherige Nachweis wird zurückgezogen.')) {
                        void run(() => reopen.mutateAsync({ employeeId: row.employee_id, year, month }))
                      }
                    }}
                  >
                    Wieder öffnen
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
          {rows.length === 0 && !overview.isLoading && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-slate-500">
                Keine Mitarbeiter in diesem Monat.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
