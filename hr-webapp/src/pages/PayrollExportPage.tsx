import { useState } from 'react'
import { FileDown } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { downloadPayrollExport, usePayrollMonthStatusQuery, type PayrollMonthStatus } from '../api/payrollExport'
import { useEmployeesQuery } from '../api/queries/employees'
import { useLocationsQuery } from '../api/queries/locations'
import { useAuth } from '../auth/AuthContext'
import { DatevExportSection } from '../components/payroll/DatevExportSection'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { formatDate, monthRange, previousYearMonth } from '../lib/format'

const ALL_LOCATIONS = '__all__'

export function PayrollExportPage() {
  const [yearMonth, setYearMonth] = useState(previousYearMonth())
  const [locationFilter, setLocationFilter] = useState(ALL_LOCATIONS)
  const [isExporting, setIsExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { canPayroll } = useAuth()
  const queryClient = useQueryClient()

  const locationsQuery = useLocationsQuery()
  const employeesQuery = useEmployeesQuery({
    locationId: locationFilter === ALL_LOCATIONS ? undefined : Number(locationFilter),
  })

  const { from, to } = monthRange(yearMonth)
  // Alle, die im Monat beschäftigt waren – auch wer im Monat ausgetreten und schon inaktiv ist.
  const employees = (employeesQuery.data ?? []).filter(
    (employee) =>
      (employee.active || Boolean(employee.termination_date)) &&
      (!employee.hire_date || employee.hire_date <= to) &&
      (!employee.termination_date || employee.termination_date >= from),
  )

  const employeeIds = employees.map((employee) => employee.id)
  const statusQuery = usePayrollMonthStatusQuery(yearMonth, employeeIds)

  async function handleExport() {
    if (employees.length === 0) {
      setError('Keine Mitarbeiter im gewählten Standort für den Export.')
      return
    }
    setIsExporting(true)
    setError(null)
    try {
      await downloadPayrollExport(employeeIds, from, to)
      void queryClient.invalidateQueries({ queryKey: ['payroll-export-status'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lohn-Export fehlgeschlagen.')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Lohn-Export</h1>
        <p className="text-sm text-slate-500">
          CSV-Export mit Soll/Ist/Saldo sowie Urlaubs-, Krankheits- und Feiertagen pro Mitarbeiter für die
          Lohnbuchhaltung. Tage mit offener oder fehlerhafter Buchung werden separat gezählt – vor dem
          Lohnlauf bitte in „Zu klären“ prüfen. Mit der Berechtigung „Vergütung &amp; Lohn-Export“ kommen Spalten für
          Zulagen und Einmalzahlungen und der DATEV-Export dazu.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="payroll_month">Monat</Label>
          <Input
            id="payroll_month"
            type="month"
            value={yearMonth}
            onChange={(event) => setYearMonth(event.target.value)}
          />
        </div>
        <div className="w-56">
          <Label>Standort</Label>
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
        <Button onClick={handleExport} disabled={isExporting}>
          <FileDown className="h-4 w-4" />
          {isExporting ? 'Exportiert…' : 'CSV exportieren'}
        </Button>
      </div>

      <p className="text-sm text-slate-500">
        Zeitraum: {formatDate(from)} – {formatDate(to)} · {employees.length} Mitarbeiter
      </p>
      {statusQuery.data && <MonthStatus status={statusQuery.data} />}

      {error && (
        <p className="text-sm text-red-600">
          {error}{' '}
          <button type="button" className="underline" onClick={() => setError(null)}>
            Schließen
          </button>
        </p>
      )}

      {canPayroll && (
        <DatevExportSection
          employeeIds={employeeIds}
          month={yearMonth}
          onExported={() => void queryClient.invalidateQueries({ queryKey: ['payroll-export-status'] })}
        />
      )}
    </div>
  )
}

/** Abschluss-Stand des Monats und bisherige Exporte – Hinweis, bevor Werte ans Lohnbüro gehen. */
function MonthStatus({ status }: { status: PayrollMonthStatus }) {
  const allClosed = status.employee_count > 0 && status.closed === status.employee_count
  return (
    <div className={`rounded-md p-3 text-sm ${allClosed ? 'bg-emerald-50 text-emerald-900' : 'bg-amber-50 text-amber-900'}`}>
      <p>
        Monatsabschluss: {status.closed} von {status.employee_count} abgeschlossen
        {status.submitted ? `, ${status.submitted} vorgelegt` : ''}
        {status.open ? `, ${status.open} offen` : ''}.
        {!allClosed && ' Solange der Monat nicht abgeschlossen ist, können sich die Werte noch ändern.'}
      </p>
      {status.exports.length > 0 && (
        <p className="mt-1">
          Schon exportiert:{' '}
          {status.exports
            .slice(0, 3)
            .map(
              (entry) =>
                `${entry.kind === 'DATEV' ? 'DATEV' : 'CSV'} am ${new Date(entry.created_at).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })}${entry.created_by ? ` von ${entry.created_by}` : ''}`,
            )
            .join(' · ')}
        </p>
      )}
    </div>
  )
}
