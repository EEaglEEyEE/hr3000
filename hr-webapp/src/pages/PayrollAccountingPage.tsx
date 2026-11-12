import { useState } from 'react'
import { ApiError } from '../api/client'
import {
  downloadPayrollAccountingFile,
  usePayrollMonthQuery,
  usePayrollReleasesQuery,
  useReleaseMonthMutation,
  useRevokeReleaseMutation,
  type AccountingEmployee,
  type AccountingMonth,
} from '../api/payrollAccounting'
import { useAuth } from '../auth/AuthContext'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { hasArea } from '../lib/access'
import { formatDate, formatDateTime, formatDays, formatHoursMinutes, formatMinutesAsHours, previousYearMonth } from '../lib/format'
import { cn } from '../lib/utils'

const CLOSURE_LABELS: Record<AccountingEmployee['closure'], string> = {
  CLOSED: 'Monat abgeschlossen',
  SUBMITTED: 'Monat vorgelegt',
  DISPUTED: 'Monat beanstandet',
  OPEN: 'Monat offen',
}

function monthLabel(month: string): string {
  const [year, number] = month.split('-').map(Number)
  return new Date(Date.UTC(year, number - 1, 1)).toLocaleDateString('de-DE', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

function euro(amount: string): string {
  return `${Number(amount).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`
}

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

/** Vorbereitende Lohnbuchhaltung: je Monat alles für das Lohnbüro, mit Freigabe (eingefroren). Wer
 * „Vergütung & Lohn“ nur ansehen darf (z. B. die Steuerberatung), sieht nur freigegebene Monate. */
export function PayrollAccountingPage() {
  const { isAdmin, perms } = useAuth()
  const canEdit = hasArea(perms, 'PAYROLL', 'EDIT')
  const releasesQuery = usePayrollReleasesQuery()
  const releases = releasesQuery.data ?? []
  const [chosen, setMonth] = useState<string | null>(canEdit ? previousYearMonth() : null)
  // Nur ansehen: ohne Auswahl den neuesten freigegebenen Monat
  const month = chosen ?? (canEdit ? null : (releases[0]?.month ?? null))
  const released = releases.some((release) => release.month === month)
  const monthQuery = usePayrollMonthQuery(month, canEdit && released)
  const release = useReleaseMonthMutation()
  const revoke = useRevokeReleaseMutation()
  const [error, setError] = useState<string | null>(null)
  const data = monthQuery.data

  function handleRelease(confirmOpenClosures = false) {
    if (!month) return
    setError(null)
    release.mutate(
      { month, confirmOpenClosures },
      {
        onError: (err) => {
          if (err instanceof ApiError && err.code === 'OPEN_CLOSURES') {
            if (window.confirm(err.message)) handleRelease(true)
            return
          }
          setError(errorText(err, 'Freigeben fehlgeschlagen.'))
        },
      },
    )
  }

  function handleRevoke() {
    if (!month || !window.confirm(`Freigabe für ${monthLabel(month)} wirklich zurücknehmen? Schnappschuss und Dateien werden gelöscht.`)) return
    setError(null)
    revoke.mutate(month, { onError: (err) => setError(errorText(err, 'Zurücknehmen fehlgeschlagen.')) })
  }

  async function handleDownload(kind: 'csv' | 'datev') {
    if (!month) return
    setError(null)
    try {
      await downloadPayrollAccountingFile(month, kind)
    } catch (err) {
      setError(errorText(err, 'Download fehlgeschlagen.'))
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Lohnbuchhaltung</h1>
        <p className="text-sm text-slate-500">
          {canEdit
            ? 'Alles für den Lohnlauf eines Monats. „Freigeben“ friert den Monat samt Exportdateien ein – das Lohnbüro sieht nur freigegebene Monate.'
            : 'Freigegebene Monate mit den Exportdateien, so wie sie freigegeben wurden.'}
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        {canEdit ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="accounting-month">Monat</Label>
            <Input
              id="accounting-month"
              type="month"
              className="w-44"
              value={month ?? ''}
              onChange={(event) => setMonth(event.target.value || null)}
            />
          </div>
        ) : (
          releases.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="accounting-release">Freigegebener Monat</Label>
              <select
                id="accounting-release"
                className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
                value={month ?? ''}
                onChange={(event) => setMonth(event.target.value)}
              >
                {releases.map((item) => (
                  <option key={item.month} value={item.month}>
                    {monthLabel(item.month)}
                  </option>
                ))}
              </select>
            </div>
          )
        )}
        {data?.release && (
          <>
            <Button variant="outline" onClick={() => void handleDownload('csv')}>
              CSV herunterladen
            </Button>
            {data.release.has_datev && (
              <Button variant="outline" onClick={() => void handleDownload('datev')}>
                DATEV LODAS herunterladen
              </Button>
            )}
          </>
        )}
        {canEdit && data && !data.release && (
          <Button onClick={() => handleRelease()} disabled={release.isPending}>
            Freigeben
          </Button>
        )}
        {isAdmin && data?.release && (
          <Button variant="outline" onClick={handleRevoke} disabled={revoke.isPending}>
            Freigabe zurücknehmen
          </Button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {!canEdit && releasesQuery.isSuccess && releases.length === 0 && (
        <p className="text-sm text-slate-500">Es ist noch kein Monat freigegeben.</p>
      )}
      {monthQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {monthQuery.isError && <p className="text-red-600">{errorText(monthQuery.error, 'Monat konnte nicht geladen werden.')}</p>}
      {data && <MonthView data={data} />}
    </div>
  )
}

function MonthView({ data }: { data: AccountingMonth }) {
  const changed = new Set(data.changed_since_release ?? [])
  const { summary } = data
  return (
    <div className="flex flex-col gap-4">
      <p
        className={cn(
          'rounded-md border p-3 text-sm',
          data.release ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-slate-200 bg-white text-slate-700',
        )}
      >
        {data.release
          ? `${monthLabel(data.month)}: freigegeben am ${formatDateTime(data.release.released_at)}${data.release.released_by ? ` von ${data.release.released_by}` : ''}.`
          : `${monthLabel(data.month)}: aktueller Stand, noch nicht freigegeben.`}
        {changed.size > 0 && ` Seit der Freigabe geändert: ${changed.size} Mitarbeiter (markiert).`}
      </p>
      {summary.open_closures > 0 && (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Bei {summary.open_closures} Mitarbeiter(n) ist der Monatsabschluss noch nicht abgeschlossen
          {data.release ? ' (Stand der Freigabe).' : '.'}
        </p>
      )}
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ['Mitarbeiter', summary.employee_count],
          ['Neuzugänge', summary.entries],
          ['Austritte', summary.exits],
          ['Monat nicht abgeschlossen', summary.open_closures],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md border border-slate-200 bg-white p-3">
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="text-lg font-semibold text-slate-900">{value}</dd>
          </div>
        ))}
      </dl>
      {data.employees.length === 0 && <p className="text-sm text-slate-500">In diesem Monat war niemand beschäftigt.</p>}
      <ul className="flex flex-col gap-3">
        {data.employees.map((employee) => (
          <EmployeeCard key={employee.employee_id} employee={employee} changed={changed.has(employee.employee_id)} />
        ))}
      </ul>
    </div>
  )
}

function EmployeeCard({ employee, changed }: { employee: AccountingEmployee; changed: boolean }) {
  const { hours } = employee
  return (
    <li
      className={cn('flex flex-col gap-3 rounded-md border bg-white p-4', changed ? 'border-amber-400' : 'border-slate-200')}
      aria-label={`${employee.first_name} ${employee.last_name}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium text-slate-900">
          {employee.last_name}, {employee.first_name}
          <span className="ml-2 text-sm font-normal text-slate-500">{employee.employee_number}</span>
        </p>
        {employee.entry && <span className="rounded-full bg-sky-100 px-2 text-xs text-sky-800">Neuzugang</span>}
        {employee.exit && <span className="rounded-full bg-slate-200 px-2 text-xs text-slate-700">Austritt</span>}
        <span
          className={cn(
            'rounded-full px-2 text-xs',
            employee.closure === 'CLOSED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800',
          )}
        >
          {CLOSURE_LABELS[employee.closure]}
        </span>
        {changed && <span className="rounded-full bg-amber-500 px-2 text-xs text-white">Seit der Freigabe geändert</span>}
      </div>
      <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Stunden</h3>
          <p>
            Soll {formatHoursMinutes(hours.target_minutes)} · Ist {formatHoursMinutes(hours.actual_minutes)} · Saldo{' '}
            {formatMinutesAsHours(hours.balance_minutes)}
          </p>
          {hours.payout_minutes > 0 && <p>Ausgezahlte Überstunden {formatHoursMinutes(hours.payout_minutes)}</p>}
          {(hours.settled_minutes ?? 0) > 0 && (
            <p>Mit dem Gehalt abgegolten {formatHoursMinutes(hours.settled_minutes ?? 0)}</p>
          )}
          {(hours.holiday_days ?? 0) > 0 && <p>Feiertage {formatDays(hours.holiday_days ?? 0)}</p>}
          {hours.open_days > 0 && <p className="text-amber-700">{hours.open_days} offene Tage</p>}
          {employee.surcharges.map((surcharge) => (
            <p key={surcharge.name}>
              Zuschlag {surcharge.name}: {formatHoursMinutes(surcharge.minutes)}
            </p>
          ))}
        </section>
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Abwesenheiten</h3>
          {employee.absences.length === 0 ? (
            <p className="text-slate-400">–</p>
          ) : (
            employee.absences.map((absence) => (
              <p key={absence.type}>
                {absence.label}: {formatDays(absence.days)} {absence.days === 1 ? 'Tag' : 'Tage'}
              </p>
            ))
          )}
        </section>
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Vergütung</h3>
          {employee.compensation ? (
            <p>
              {euro(employee.compensation.amount)} {employee.compensation.pay_type === 'HOURLY' ? 'je Stunde' : 'je Monat'}
            </p>
          ) : (
            <p className="text-slate-400">Keine Vergütung hinterlegt</p>
          )}
          {(employee.pay_components ?? []).map((component) => (
            <p key={component.name}>
              {component.name}: {euro(component.amount)}
            </p>
          ))}
        </section>
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Änderungen im Monat</h3>
          {employee.changes.length === 0 ? (
            <p className="text-slate-400">–</p>
          ) : (
            employee.changes.map((change, index) => (
              <p key={index}>
                {formatDate(change.date)}: {change.text}
              </p>
            ))
          )}
        </section>
      </div>
    </li>
  )
}
