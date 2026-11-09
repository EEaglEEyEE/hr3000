/** Migration aus einem Altsystem: Werte bestehender Mitarbeiter (Überstunden-Übertrag, Urlaubskonto,
 *  Arbeitszeitmodell) per CSV zu einem Stichtag übernehmen – erst Vorschau, dann übernehmen. */
import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { uploadMigrationValues, type MigrationImportResult } from '../../api/employeeImport'
import { formatDate, todayIsoDate } from '../../lib/format'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

const COLUMNS = [
  'saldo_stunden',
  'urlaubsanspruch_tage',
  'uebertrag_vorjahr_tage',
  'wochenstunden',
  'arbeitstage',
  'tagesstunden',
  'monatsstunden',
  'monatsgrenze',
  'pause_minuten',
]

export function MigrationValuesSection() {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [cutover, setCutover] = useState(todayIsoDate())
  const [result, setResult] = useState<MigrationImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send(apply: boolean) {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const response = await uploadMigrationValues(file, cutover, apply)
      setResult(response)
      if (apply && response.rows.length > 0) {
        void queryClient.invalidateQueries({ queryKey: ['employees'] })
        setFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Übernahme fehlgeschlagen.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div className="text-sm text-slate-700">
        <p className="font-medium text-slate-900">Werte aus dem Altsystem übernehmen</p>
        <p>
          Für bestehende Mitarbeiter (Zuordnung über die Personalnummer), alles zum Stichtag: Überstunden-Übertrag in Stunden
          (auch negativ), Urlaubsanspruch und Übertrag aus dem Vorjahr für das Jahr des Stichtags, Arbeitszeitmodell ab
          Stichtag (Spalten wie oben, dazu <code className="rounded bg-slate-100 px-1">monatsstunden</code> mit
          Arbeitstagen und <code className="rounded bg-slate-100 px-1">pause_minuten</code>). Pflichtspalte{' '}
          <code className="rounded bg-slate-100 px-1">personalnummer</code>, weitere Spalten:{' '}
          <code className="rounded bg-slate-100 px-1">{COLUMNS.join(', ')}</code>. Leere Zellen ändern nichts.
        </p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="migration_cutover">Stichtag</Label>
          <Input
            id="migration_cutover"
            type="date"
            className="w-44"
            value={cutover}
            onChange={(e) => {
              setCutover(e.target.value)
              setResult(null)
            }}
          />
        </div>
        <input
          ref={fileInputRef}
          type="file"
          aria-label="CSV-Datei mit Werten aus dem Altsystem"
          accept=".csv,text/csv"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null)
            setResult(null)
          }}
          className="max-w-full text-sm text-slate-700"
        />
        <Button type="button" variant="outline" disabled={!file || !cutover || busy} onClick={() => void send(false)}>
          Vorschau
        </Button>
        <Button
          type="button"
          disabled={!file || !cutover || busy || !result || result.applied || result.rows.length === 0}
          onClick={() => void send(true)}
        >
          Übernehmen
        </Button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {result && (
        <div className="flex flex-col gap-3">
          <p className={result.applied ? 'text-sm text-emerald-600' : 'text-sm text-slate-700'}>
            {result.applied
              ? `Werte für ${result.rows.length} Mitarbeiter zum ${formatDate(cutover)} übernommen.`
              : `Vorschau: ${result.rows.length} Mitarbeiter würden zum ${formatDate(cutover)} geändert.`}
            {result.errors.length > 0 ? ` ${result.errors.length} Zeile(n) mit Fehler werden übersprungen.` : ''}
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Zeile</TableHead>
                <TableHead>Mitarbeiter</TableHead>
                <TableHead>Änderungen bzw. Fehler</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[
                ...result.rows.map((row) => ({ line: row.row, who: `${row.name} (${row.employee_number})`, text: row.changes.join(' · '), bad: false })),
                ...result.errors.map((rowError) => ({ line: rowError.row, who: '', text: rowError.message, bad: true })),
              ]
                .sort((a, b) => a.line - b.line)
                .map((entry) => (
                  <TableRow key={`${entry.line}-${entry.bad}`}>
                    <TableCell>{entry.bad ? <Badge variant="danger">Zeile {entry.line}</Badge> : `Zeile ${entry.line}`}</TableCell>
                    <TableCell>{entry.who}</TableCell>
                    <TableCell className={entry.bad ? 'text-red-700' : ''}>{entry.text}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}
