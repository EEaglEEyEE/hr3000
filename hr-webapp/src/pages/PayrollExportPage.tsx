import { useState } from 'react'
import { FileDown } from 'lucide-react'
import { downloadPayrollExport } from '../api/payrollExport'
import { useEmployeesQuery } from '../api/queries/employees'
import { useLocationsQuery } from '../api/queries/locations'
import { useAuth } from '../auth/AuthContext'
import { DatevExportSection } from '../components/payroll/DatevExportSection'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { currentYearMonth, formatDate, monthRange } from '../lib/format'

const ALL_LOCATIONS = '__all__'

export function PayrollExportPage() {
  const [yearMonth, setYearMonth] = useState(currentYearMonth())
  const [locationFilter, setLocationFilter] = useState(ALL_LOCATIONS)
  const [isExporting, setIsExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { isAdmin } = useAuth()

  const locationsQuery = useLocationsQuery()
  const employeesQuery = useEmployeesQuery({
    locationId: locationFilter === ALL_LOCATIONS ? undefined : Number(locationFilter),
    active: true,
  })

  const employees = employeesQuery.data ?? []
  const { from, to } = monthRange(yearMonth)

  async function handleExport() {
    if (employees.length === 0) {
      setError('Keine Mitarbeiter im gewählten Standort für den Export.')
      return
    }
    setIsExporting(true)
    setError(null)
    try {
      await downloadPayrollExport(
        employees.map((employee) => employee.id),
        from,
        to,
      )
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
          Lohnlauf bitte in „Zu klären“ prüfen. Zieht ein Admin den Export, kommen Spalten für Zulagen und
          Einmalzahlungen dazu.
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

      {error && (
        <p className="text-sm text-red-600">
          {error}{' '}
          <button type="button" className="underline" onClick={() => setError(null)}>
            Schließen
          </button>
        </p>
      )}

      {isAdmin && <DatevExportSection employeeIds={employees.map((employee) => employee.id)} month={yearMonth} />}
    </div>
  )
}
