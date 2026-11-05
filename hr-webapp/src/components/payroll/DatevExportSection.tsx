/** DATEV LODAS (nur Admin): Zuordnung (Berater-/Mandantennummer, Lohnarten) und Export der
 *  Bewegungsdaten eines Monats als ASCII-Importdatei – mit Vorschau und Hinweisen. */
import { useEffect, useState } from 'react'
import { FileDown } from 'lucide-react'
import { downloadDatevExport, fetchDatevPreview, type DatevPreview } from '../../api/payrollExport'
import { useSettingsQuery, useUpdateSettingsMutation } from '../../api/queries/settings'
import { useSetSurchargeWageTypeMutation, useSurchargeRulesQuery } from '../../api/queries/surcharges'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

export function DatevExportSection({ employeeIds, month }: { employeeIds: number[]; month: string }) {
  const settingsQuery = useSettingsQuery()
  const updateSettings = useUpdateSettingsMutation()
  const rulesQuery = useSurchargeRulesQuery()
  const setRuleWageType = useSetSurchargeWageTypeMutation()
  const settings = settingsQuery.data

  const [consultant, setConsultant] = useState('')
  const [client, setClient] = useState('')
  const [hoursWageType, setHoursWageType] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<DatevPreview | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!settings) return
    setConsultant(settings.datev_consultant_number ?? '')
    setClient(settings.datev_client_number ?? '')
    setHoursWageType(settings.datev_hours_wage_type ?? '')
  }, [settings])
  // Andere Auswahl = alte Vorschau ungültig
  useEffect(() => setPreview(null), [month, employeeIds.length])

  const configured = Boolean(settings?.datev_consultant_number && settings?.datev_client_number)
  const configValid = /^\d{4,7}$/.test(consultant) && /^\d{1,5}$/.test(client) && /^\d{0,6}$/.test(hoursWageType)

  async function run(action: () => Promise<void>) {
    setError(null)
    setMessage(null)
    setBusy(true)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'DATEV-Export fehlgeschlagen.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-md border border-slate-200 bg-white p-4">
      <div>
        <h2 className="font-medium text-slate-900">DATEV LODAS</h2>
        <p className="text-sm text-slate-500">
          Importdatei mit den Bewegungsdaten des Monats für das Lohnbüro (LODAS: ASCII-Import). Übertragen werden Ist-Stunden
          von Mitarbeitern mit Stundenlohn, Zuschlagsstunden und Zulagen/Einmalzahlungen – jeweils nur mit Lohnart.
          Urlaub und Krankheit überträgt die Datei nicht. Den Aufbau einmal mit dem Lohnbüro per Testimport abstimmen.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="datev_consultant">Beraternummer</Label>
          <Input id="datev_consultant" inputMode="numeric" className="w-32" value={consultant} onChange={(e) => setConsultant(e.target.value.trim())} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="datev_client">Mandantennummer</Label>
          <Input id="datev_client" inputMode="numeric" className="w-28" value={client} onChange={(e) => setClient(e.target.value.trim())} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="datev_hours">Lohnart Ist-Stunden</Label>
          <Input id="datev_hours" inputMode="numeric" className="w-28" value={hoursWageType} onChange={(e) => setHoursWageType(e.target.value.trim())} />
        </div>
        <Button
          variant="outline"
          disabled={!configValid || updateSettings.isPending}
          onClick={() =>
            void run(async () => {
              await updateSettings.mutateAsync({
                datev_consultant_number: consultant,
                datev_client_number: client,
                datev_hours_wage_type: hoursWageType,
              })
              setMessage('DATEV-Einstellungen gespeichert.')
            })
          }
        >
          Speichern
        </Button>
      </div>
      <p className="-mt-2 text-xs text-slate-500">
        Beraternummer 4–7 Ziffern, Mandantennummer 1–5 Ziffern. Ist-Stunden gehen nur für Zeiträume mit Vergütung
        „Stundenlohn“ in die Datei. Lohnarten für Zulagen stehen beim Mitarbeiter unter „Vertrag &amp; Vergütung“.
      </p>

      {(rulesQuery.data?.length ?? 0) > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-sm font-medium text-slate-700">Lohnarten für Zuschläge</p>
          <div className="flex flex-wrap gap-3">
            {rulesQuery.data!.map((rule) => (
              <label key={rule.id} className="flex items-center gap-2 text-sm">
                {rule.name}
                <Input
                  aria-label={`Lohnart ${rule.name}`}
                  inputMode="numeric"
                  className="w-24"
                  defaultValue={rule.wage_type ?? ''}
                  onBlur={(e) => {
                    const value = e.target.value.trim()
                    if (value !== (rule.wage_type ?? '') && /^\d{0,6}$/.test(value)) {
                      void run(async () => {
                        await setRuleWageType.mutateAsync({ id: rule.id, wageType: value })
                      })
                    }
                  }}
                />
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={!configured || busy || employeeIds.length === 0}
          onClick={() => void run(async () => setPreview(await fetchDatevPreview(employeeIds, month)))}
        >
          Vorschau
        </Button>
        <Button
          disabled={!configured || busy || employeeIds.length === 0}
          onClick={() => void run(() => downloadDatevExport(employeeIds, month))}
        >
          <FileDown className="h-4 w-4" />
          DATEV-Datei herunterladen
        </Button>
      </div>
      {!configured && <p className="text-sm text-slate-500">Für den Export zuerst Berater- und Mandantennummer speichern.</p>}
      {message && <p className="text-sm text-emerald-600">{message}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {preview && (
        <div className="flex flex-col gap-3">
          {preview.warnings.length > 0 && (
            <div className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">
              <p className="font-medium">Hinweise</p>
              <ul className="ml-4 list-disc">
                {preview.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pers.-Nr.</TableHead>
                <TableHead>Mitarbeiter</TableHead>
                <TableHead>Lohnart</TableHead>
                <TableHead>Wert</TableHead>
                <TableHead>Inhalt</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {preview.lines.map((line) => (
                <TableRow key={`${line.personnel_number}-${line.wage_type}-${line.key}`}>
                  <TableCell>{line.personnel_number}</TableCell>
                  <TableCell>{line.name}</TableCell>
                  <TableCell>{line.wage_type}</TableCell>
                  <TableCell>
                    {line.value.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}{' '}
                    {line.key === '01' ? 'Std.' : 'EUR'}
                  </TableCell>
                  <TableCell className="text-slate-600">{line.label}</TableCell>
                </TableRow>
              ))}
              {preview.lines.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-slate-500">
                    Keine Buchungen für diesen Monat.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}
