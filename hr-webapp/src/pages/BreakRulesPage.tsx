import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  useBreakRulesQuery,
  useCreateBreakRuleMutation,
  useDeleteBreakRuleMutation,
  useUpdateBreakRuleMutation,
} from '../api/queries/breakRules'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { formatDate, todayIsoDate } from '../lib/format'

export function BreakRulesPage() {
  const rulesQuery = useBreakRulesQuery()
  const createRule = useCreateBreakRuleMutation()
  const updateRule = useUpdateBreakRuleMutation()
  const deleteRule = useDeleteBreakRuleMutation()

  const [minWorkMinutes, setMinWorkMinutes] = useState(360)
  const [deductMinutes, setDeductMinutes] = useState(30)
  // Gilt für Anlegen, Ändern und Beenden: frühere Tage behalten die alte Staffel.
  const [validFrom, setValidFrom] = useState(todayIsoDate())
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Speichern fehlgeschlagen.')
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await run(async () => {
      await createRule.mutateAsync({ min_work_minutes: minWorkMinutes, deduct_minutes: deductMinutes, valid_from: validFrom })
      setMinWorkMinutes(360)
      setDeductMinutes(30)
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Pausenregeln</h1>
        <p className="text-sm text-slate-500">
          Gesetzliche Pausenstaffel nach §4 ArbZG: ab wie vielen Arbeitsminuten wird wie viel Pause
          abgezogen bzw. – wenn bei einem Mitarbeiter aktiviert – automatisch gestempelt. Änderungen gelten ab dem
          gewählten Stichtag; Tage davor (und bereits abgeschlossene Monate) rechnen mit der bisherigen Staffel.
        </p>
      </div>

      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="valid_from">Änderungen gültig ab</Label>
          <Input id="valid_from" type="date" className="w-44" value={validFrom} onChange={(e) => e.target.value && setValidFrom(e.target.value)} />
        </div>
      </div>

      {rulesQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {rulesQuery.isError && <p className="text-red-600">Pausenregeln konnten nicht geladen werden.</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {rulesQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ab Arbeitsminuten</TableHead>
              <TableHead>Pausenabzug (Minuten)</TableHead>
              <TableHead>Gültig</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rulesQuery.data.map((rule) => (
              <TableRow key={rule.id}>
                <TableCell>
                  <Input
                    type="number"
                    min={0}
                    className="w-28"
                    defaultValue={rule.min_work_minutes}
                    onBlur={(event) => {
                      const value = Number(event.target.value)
                      if (value !== rule.min_work_minutes) {
                        void run(() => updateRule.mutateAsync({ ruleId: rule.id, payload: { min_work_minutes: value, valid_from: validFrom } }))
                      }
                    }}
                  />
                </TableCell>
                <TableCell>
                  <Input
                    type="number"
                    min={0}
                    className="w-28"
                    defaultValue={rule.deduct_minutes}
                    onBlur={(event) => {
                      const value = Number(event.target.value)
                      if (value !== rule.deduct_minutes) {
                        void run(() => updateRule.mutateAsync({ ruleId: rule.id, payload: { deduct_minutes: value, valid_from: validFrom } }))
                      }
                    }}
                  />
                </TableCell>
                <TableCell className="text-sm text-slate-600">
                  {rule.valid_from > '2000-01-01' ? `ab ${formatDate(rule.valid_from)}` : 'seit Beginn'}
                  {rule.valid_to && ` bis ${formatDate(rule.valid_to)}`}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    title={`Regel ab ${formatDate(validFrom)} beenden`}
                    onClick={() => {
                      if (window.confirm(`Regel ab ${formatDate(validFrom)} nicht mehr anwenden?`)) {
                        void run(() => deleteRule.mutateAsync({ ruleId: rule.id, validFrom }))
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {rulesQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-slate-500">
                  Noch keine Pausenregel angelegt.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <form className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleCreate}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="min_work_minutes">Ab Arbeitsminuten</Label>
          <Input
            id="min_work_minutes"
            type="number"
            min={0}
            className="w-32"
            value={minWorkMinutes}
            onChange={(event) => setMinWorkMinutes(Number(event.target.value) || 0)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="deduct_minutes">Pausenabzug (Minuten)</Label>
          <Input
            id="deduct_minutes"
            type="number"
            min={0}
            className="w-32"
            value={deductMinutes}
            onChange={(event) => setDeductMinutes(Number(event.target.value) || 0)}
          />
        </div>
        <Button type="submit" disabled={createRule.isPending}>
          <Plus className="h-4 w-4" />
          Regel hinzufügen (ab {formatDate(validFrom)})
        </Button>
      </form>
    </div>
  )
}
