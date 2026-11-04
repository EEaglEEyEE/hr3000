import { useState } from 'react'
import { FileDown, Printer } from 'lucide-react'
import { downloadShiftPlanPdf } from '../api/shiftPlanPdf'
import { useEmployeesQuery } from '../api/queries/employees'
import { useLocationsQuery } from '../api/queries/locations'
import { useShiftTemplatesQuery } from '../api/queries/shiftTemplates'
import { EmployeeShiftRow } from '../components/shiftplanning/EmployeeShiftRow'
import { ShiftTemplatePalette } from '../components/shiftplanning/ShiftTemplatePalette'
import { Button } from '../components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { addDaysIsoDate, formatDate, mondayOfWeek, todayIsoDate, weekdayShortLabel } from '../lib/format'

const ALL_LOCATIONS = '__all__'

export function ShiftPlanCalendarPage() {
  const [weekStart, setWeekStart] = useState(() => mondayOfWeek(todayIsoDate()))
  const [locationFilter, setLocationFilter] = useState(ALL_LOCATIONS)
  const [error, setError] = useState<string | null>(null)
  const [isExportingPdf, setIsExportingPdf] = useState(false)

  const locationsQuery = useLocationsQuery()
  const employeesQuery = useEmployeesQuery({
    locationId: locationFilter === ALL_LOCATIONS ? undefined : Number(locationFilter),
    active: true,
  })
  const templatesQuery = useShiftTemplatesQuery()

  const weekDates = Array.from({ length: 7 }, (_, index) => addDaysIsoDate(weekStart, index))
  const templates = templatesQuery.data ?? []
  const templateById = new Map(templates.map((template) => [template.id, template]))
  // Wochen-/Monatssoll-Vorlagen sind nur als Standard-Schicht zuweisbar
  // (siehe ShiftTemplateFormDialog), nicht als einzelner Ausnahme-Tag –
  // die Palette bietet daher nur Tagessoll-Vorlagen zum Ziehen an.
  const dailyTemplates = templates.filter((template) => template.target_period === 'DAILY')
  const employees = [...(employeesQuery.data ?? [])].sort((a, b) => a.last_name.localeCompare(b.last_name))

  async function handlePdfExport() {
    if (employees.length === 0) {
      setError('Keine Mitarbeiter im gewählten Standort für den PDF-Export.')
      return
    }
    setIsExportingPdf(true)
    setError(null)
    try {
      await downloadShiftPlanPdf(employees.map((employee) => employee.id), weekDates[0], weekDates[6])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF-Export fehlgeschlagen.')
    } finally {
      setIsExportingPdf(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between print:hidden">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Schichtplan-Kalender</h1>
          <p className="text-sm text-slate-500">
            Schichtvorlage aus der Palette auf einen Tag ziehen, um sie zuzuweisen. Bereits zugewiesene
            Schichten (blau hinterlegt) können auf einen anderen Tag verschoben werden.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handlePdfExport} disabled={isExportingPdf}>
            <FileDown className="h-4 w-4" />
            {isExportingPdf ? 'Exportiert…' : 'PDF exportieren'}
          </Button>
          <Button variant="outline" onClick={() => window.print()}>
            <Printer className="h-4 w-4" />
            Drucken
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 print:hidden">
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
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setWeekStart((current) => addDaysIsoDate(current, -7))}>
            ← Vorherige Woche
          </Button>
          <span className="text-sm text-slate-600">
            {formatDate(weekStart)} – {formatDate(addDaysIsoDate(weekStart, 6))}
          </span>
          <Button variant="outline" size="sm" onClick={() => setWeekStart((current) => addDaysIsoDate(current, 7))}>
            Nächste Woche →
          </Button>
          <Button variant="outline" size="sm" onClick={() => setWeekStart(mondayOfWeek(todayIsoDate()))}>
            Heute
          </Button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-600 print:hidden">
          {error}{' '}
          <button type="button" className="underline" onClick={() => setError(null)}>
            Schließen
          </button>
        </p>
      )}

      <div className="print:mb-2 print:block">
        <h2 className="hidden text-base font-semibold text-slate-900 print:block">
          Schichtplan {formatDate(weekStart)} – {formatDate(addDaysIsoDate(weekStart, 6))}
        </h2>
      </div>

      <div className="flex gap-4">
        <div className="flex-1 overflow-x-auto rounded-md border border-slate-200 bg-white">
          {employeesQuery.isLoading && <p className="p-4 text-slate-500">Lädt…</p>}
          {employeesQuery.isError && (
            <p className="p-4 text-red-600">Mitarbeiter konnten nicht geladen werden.</p>
          )}
          {employeesQuery.data && (
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="border-b border-slate-200 px-2 py-2 text-left text-xs font-medium text-slate-500">
                    Mitarbeiter
                  </th>
                  {weekDates.map((isoDate) => (
                    <th
                      key={isoDate}
                      className="border-b border-slate-200 px-2 py-2 text-left text-xs font-medium text-slate-500"
                    >
                      {weekdayShortLabel(isoDate)} {formatDate(isoDate)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {employees.map((employee) => (
                  <EmployeeShiftRow
                    key={employee.id}
                    employee={employee}
                    weekDates={weekDates}
                    templateById={templateById}
                    readOnly={false}
                    onError={setError}
                  />
                ))}
                {employees.length === 0 && (
                  <tr>
                    <td colSpan={8} className="p-4 text-center text-slate-500">
                      Keine Mitarbeiter im gewählten Standort.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        <ShiftTemplatePalette templates={dailyTemplates} />
      </div>
    </div>
  )
}
