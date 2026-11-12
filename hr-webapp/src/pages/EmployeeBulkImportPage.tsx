import { useRef, useState, type ChangeEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Upload } from 'lucide-react'
import { uploadEmployeeBulkImport, type BulkImportResult } from '../api/employeeImport'
import { useLocationsQuery } from '../api/queries/locations'
import { useDepartmentsQuery } from '../api/queries/departments'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { MigrationValuesSection } from '../components/migration/MigrationValuesSection'

const REQUIRED_COLUMNS = ['vorname', 'nachname', 'personalnummer', 'standort']
const OPTIONAL_COLUMNS = [
  'abteilung',
  'aktiv',
  'login_email',
  'eintrittsdatum',
  'geburtsdatum',
  'wochenstunden',
  'arbeitstage',
  'tagesstunden',
  'tagesstunden_woche2',
  'tagesstunden_woche3',
  'tagesstunden_woche4',
  'turnus_beginn',
  'monatsgrenze',
  'abgegoltene_ueberstunden',
]

export function EmployeeBulkImportPage() {
  const queryClient = useQueryClient()
  const locationsQuery = useLocationsQuery()
  const departmentsQuery = useDepartmentsQuery()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [result, setResult] = useState<BulkImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(event.target.files?.[0] ?? null)
    setResult(null)
    setError(null)
  }

  async function handleImport() {
    if (!selectedFile) return
    setIsUploading(true)
    setError(null)
    setResult(null)
    try {
      const importResult = await uploadEmployeeBulkImport(selectedFile)
      setResult(importResult)
      if (importResult.created > 0) {
        void queryClient.invalidateQueries({ queryKey: ['employees'] })
      }
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import fehlgeschlagen.')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Mitarbeiter-Import</h1>
        <p className="text-sm text-slate-500">
          Legt mehrere Mitarbeiter auf einmal per CSV-Datei an.{' '}
          <Link to="/mitarbeiter" className="underline">
            Zurück zur Mitarbeiterliste
          </Link>
          .
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
        <div className="text-sm text-slate-700">
          <p className="font-medium text-slate-900">Format</p>
          <p>
            Semikolon-getrennte CSV, UTF-8. Erste Zeile = Spaltenüberschriften. Pflichtspalten:{' '}
            <code className="rounded bg-slate-100 px-1">{REQUIRED_COLUMNS.join(', ')}</code>. Optionale
            Spalten: <code className="rounded bg-slate-100 px-1">{OPTIONAL_COLUMNS.join(', ')}</code> (Aktiv:
            ja/nein, Standardwert ja; Datumsfelder im Format JJJJ-MM-TT; Arbeitszeitmodell: Wochenstunden z. B. „38,5“
            und Arbeitstage z. B. „Mo-Fr“ oder „Mo,Mi,Fr“, oder für Teilzeit Tagesstunden z. B. „Mo:8,Di:8,Mi:4.5“; nur Wochenstunden ohne Arbeitstage = flexibel ohne feste Tage; Arbeitstage „nach Aufwand“ = Aushilfe ohne Soll, optional mit Monatsgrenze in Stunden – gilt ab
            Anstelldatum).
          </p>
          <p className="mt-1">
            Mehrwöchiges Modell (Turnus über 2 bis 4 Wochen): Woche 1 in „tagesstunden“, die weiteren Wochen lückenlos in
            „tagesstunden_woche2“ bis „tagesstunden_woche4“; „turnus_beginn“ (optional) nennt einen Tag der Woche 1, sonst
            beginnt der Turnus in der Woche des Anstelldatums. „abgegoltene_ueberstunden“: Stunden je Monat, die mit dem
            Gehalt abgegolten sind (z. B. „10“), nur zusammen mit einem Arbeitszeitmodell in derselben Zeile.
          </p>
        </div>

        <div className="text-sm text-slate-700">
          <p className="font-medium text-slate-900">Gültige Standort-Namen</p>
          <p>
            {locationsQuery.data && locationsQuery.data.length > 0
              ? locationsQuery.data.map((location) => location.name).join(', ')
              : 'Noch keine Standorte angelegt.'}
          </p>
        </div>

        {departmentsQuery.data && departmentsQuery.data.length > 0 && (
          <div className="text-sm text-slate-700">
            <p className="font-medium text-slate-900">Gültige Abteilungs-Namen</p>
            <p>{departmentsQuery.data.map((department) => department.name).join(', ')}</p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 pt-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
            className="max-w-full text-sm text-slate-700"
          />
          <Button type="button" disabled={!selectedFile || isUploading} onClick={handleImport}>
            <Upload className="h-4 w-4" />
            {isUploading ? 'Importiere…' : 'Importieren'}
          </Button>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      {result && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-emerald-600">
            {result.created} Mitarbeiter angelegt
            {result.errors.length > 0 ? `, ${result.errors.length} Zeile(n) mit Fehler übersprungen.` : '.'}
          </p>

          {result.errors.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Zeile</TableHead>
                  <TableHead>Fehler</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.errors.map((rowError, index) => (
                  <TableRow key={index}>
                    <TableCell>
                      <Badge variant="danger">Zeile {rowError.row}</Badge>
                    </TableCell>
                    <TableCell>{rowError.message}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}

      <MigrationValuesSection />
    </div>
  )
}
