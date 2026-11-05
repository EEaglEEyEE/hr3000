import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  useBreakRulesQuery,
  useCreateBreakRuleMutation,
  useDeleteBreakRuleMutation,
  useUpdateBreakRuleMutation,
  type BreakRule,
  type BreakRuleUpdateRequest,
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
  // Feste Pause des Betriebs: feste Minuten ab einer Arbeitszeit oder feste Uhrzeit.
  const [fixedKind, setFixedKind] = useState<'FIXED_MINUTES' | 'FIXED_WINDOW'>('FIXED_WINDOW')
  const [fixedThreshold, setFixedThreshold] = useState(0)
  const [fixedMinutes, setFixedMinutes] = useState(30)
  const [windowStart, setWindowStart] = useState('12:00')
  const [windowEnd, setWindowEnd] = useState('12:30')
  // Gilt für Anlegen, Ändern und Beenden: frühere Tage behalten die alte Regel.
  const [validFrom, setValidFrom] = useState(todayIsoDate())
  const [error, setError] = useState<string | null>(null)

  const rules = rulesQuery.data ?? []
  const legal = rules.filter((rule) => rule.kind === 'LEGAL')
  const fixed = rules.filter((rule) => rule.kind !== 'LEGAL')

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Speichern fehlgeschlagen. Bitte die Angaben prüfen.')
    }
  }

  function update(rule: BreakRule, payload: BreakRuleUpdateRequest) {
    void run(() => updateRule.mutateAsync({ ruleId: rule.id, payload: { ...payload, valid_from: validFrom } }))
  }

  function end(rule: BreakRule) {
    if (window.confirm(`Regel ab ${formatDate(validFrom)} nicht mehr anwenden?`)) {
      void run(() => deleteRule.mutateAsync({ ruleId: rule.id, validFrom }))
    }
  }

  async function handleCreateLegal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await run(async () => {
      await createRule.mutateAsync({ kind: 'LEGAL', min_work_minutes: minWorkMinutes, deduct_minutes: deductMinutes, valid_from: validFrom })
      setMinWorkMinutes(360)
      setDeductMinutes(30)
    })
  }

  async function handleCreateFixed(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await run(() =>
      createRule.mutateAsync(
        fixedKind === 'FIXED_WINDOW'
          ? { kind: 'FIXED_WINDOW', start_time: windowStart, end_time: windowEnd, valid_from: validFrom }
          : { kind: 'FIXED_MINUTES', min_work_minutes: fixedThreshold, deduct_minutes: fixedMinutes, valid_from: validFrom },
      ),
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Pausenregeln</h1>
        <p className="text-sm text-slate-500">
          Wie viel Pause von der Anwesenheit abgezogen wird. Änderungen gelten ab dem gewählten Stichtag; Tage davor (und
          bereits abgeschlossene Monate) rechnen mit den bisherigen Regeln.
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

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-medium text-slate-900">Gesetzliche Pausenstaffel</h2>
          <p className="text-sm text-slate-500">
            Nach §4 ArbZG: ab wie vielen Arbeitsminuten mindestens wie viel Pause. Gestempelte Pausen zählen mit, nur was
            fehlt, wird abgezogen bzw. – wenn beim Mitarbeiter aktiviert – automatisch gestempelt. Die Staffel gilt immer als
            Untergrenze, auch neben festen Pausen.
          </p>
        </div>
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
              {legal.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>
                    <NumberCell value={rule.min_work_minutes} onCommit={(value) => update(rule, { min_work_minutes: value })} />
                  </TableCell>
                  <TableCell>
                    <NumberCell value={rule.deduct_minutes} onCommit={(value) => update(rule, { deduct_minutes: value })} />
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{validity(rule)}</TableCell>
                  <TableCell>
                    <EndButton validFrom={validFrom} onClick={() => end(rule)} />
                  </TableCell>
                </TableRow>
              ))}
              {legal.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-slate-500">
                    Noch keine Pausenregel angelegt.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}

        <form className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleCreateLegal}>
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
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-medium text-slate-900">Feste Pausen des Betriebs</h2>
          <p className="text-sm text-slate-500">
            Für alle Mitarbeiter, auch ohne Pausenstempelung. <strong>Feste Uhrzeit</strong> (z. B. 12:00–12:30): abgezogen,
            soweit der Mitarbeiter in dieser Zeit da war. <strong>Feste Minuten</strong>: ab einer Arbeitszeit mindestens so viel
            Pause; gestempelte Pausen zählen mit. Ein Arbeitszeitmodell oder eine Schichtvorlage mit eigener Pause ersetzt diese
            Regeln für den Mitarbeiter.
          </p>
        </div>
        {rulesQuery.data && fixed.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Art</TableHead>
                <TableHead>Regel</TableHead>
                <TableHead>Gültig</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {fixed.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell className="text-sm">{rule.kind === 'FIXED_WINDOW' ? 'Feste Uhrzeit' : 'Feste Minuten'}</TableCell>
                  <TableCell>
                    {rule.kind === 'FIXED_WINDOW' ? (
                      <div className="flex items-center gap-2 text-sm">
                        <TimeCell label="Pause von" value={rule.start_time} onCommit={(value) => update(rule, { start_time: value })} />
                        bis
                        <TimeCell label="Pause bis" value={rule.end_time} onCommit={(value) => update(rule, { end_time: value })} />
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        ab
                        <NumberCell value={rule.min_work_minutes} onCommit={(value) => update(rule, { min_work_minutes: value })} />
                        Arbeitsminuten mindestens
                        <NumberCell value={rule.deduct_minutes} onCommit={(value) => update(rule, { deduct_minutes: value })} />
                        Minuten
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{validity(rule)}</TableCell>
                  <TableCell>
                    <EndButton validFrom={validFrom} onClick={() => end(rule)} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <form className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleCreateFixed}>
          <div className="flex flex-wrap gap-2 text-sm">
            {(
              [
                ['FIXED_WINDOW', 'Feste Uhrzeit'],
                ['FIXED_MINUTES', 'Feste Minuten'],
              ] as const
            ).map(([kind, label]) => (
              <Button
                key={kind}
                type="button"
                size="sm"
                variant={fixedKind === kind ? 'default' : 'outline'}
                aria-pressed={fixedKind === kind}
                onClick={() => setFixedKind(kind)}
              >
                {label}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {fixedKind === 'FIXED_WINDOW' ? (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="window_start">Pause von</Label>
                  <Input id="window_start" type="time" className="w-32" value={windowStart} onChange={(e) => setWindowStart(e.target.value)} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="window_end">Pause bis</Label>
                  <Input id="window_end" type="time" className="w-32" value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} />
                </div>
              </>
            ) : (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="fixed_threshold">Ab Arbeitsminuten</Label>
                  <Input
                    id="fixed_threshold"
                    type="number"
                    min={0}
                    className="w-32"
                    value={fixedThreshold}
                    onChange={(event) => setFixedThreshold(Number(event.target.value) || 0)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="fixed_minutes">Pause (Minuten)</Label>
                  <Input
                    id="fixed_minutes"
                    type="number"
                    min={1}
                    className="w-32"
                    value={fixedMinutes}
                    onChange={(event) => setFixedMinutes(Number(event.target.value) || 0)}
                  />
                </div>
              </>
            )}
            <Button
              type="submit"
              disabled={createRule.isPending || (fixedKind === 'FIXED_WINDOW' ? !(windowStart && windowEnd && windowStart < windowEnd) : fixedMinutes < 1)}
            >
              <Plus className="h-4 w-4" />
              Feste Pause hinzufügen (ab {formatDate(validFrom)})
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}

function validity(rule: BreakRule): string {
  return `${rule.valid_from > '2000-01-01' ? `ab ${formatDate(rule.valid_from)}` : 'seit Beginn'}${rule.valid_to ? ` bis ${formatDate(rule.valid_to)}` : ''}`
}

function NumberCell({ value, onCommit }: { value: number; onCommit: (value: number) => void }) {
  return (
    <Input
      type="number"
      min={0}
      className="w-28"
      defaultValue={value}
      onBlur={(event) => {
        const next = Number(event.target.value)
        if (next !== value) onCommit(next)
      }}
    />
  )
}

function TimeCell({ label, value, onCommit }: { label: string; value: string | null; onCommit: (value: string) => void }) {
  const current = value?.slice(0, 5) ?? ''
  return (
    <Input
      type="time"
      aria-label={label}
      className="w-32"
      defaultValue={current}
      onBlur={(event) => {
        if (event.target.value && event.target.value !== current) onCommit(event.target.value)
      }}
    />
  )
}

function EndButton({ validFrom, onClick }: { validFrom: string; onClick: () => void }) {
  return (
    <Button variant="ghost" size="icon" title={`Regel ab ${formatDate(validFrom)} beenden`} onClick={onClick}>
      <Trash2 className="h-4 w-4 text-red-600" />
    </Button>
  )
}
