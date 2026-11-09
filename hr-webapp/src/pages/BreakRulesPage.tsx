import { useEffect, useState, type FormEvent } from 'react'
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
import { useSettingsQuery, useUpdateSettingsMutation } from '../api/queries/settings'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { formatDate, todayIsoDate } from '../lib/format'

/** Alles zu Pausen an einer Stelle: gesetzliche Mindestpause, Pausenstaffel, feste Pausenzeiten,
 *  Berechnung und automatisches Stempeln. Je Mitarbeiter abweichend: Arbeitszeitmodell → „Pause“. */
export function BreakRulesPage() {
  const rulesQuery = useBreakRulesQuery()
  const createRule = useCreateBreakRuleMutation()
  const updateRule = useUpdateBreakRuleMutation()
  const deleteRule = useDeleteBreakRuleMutation()
  const settingsQuery = useSettingsQuery()
  const updateSettings = useUpdateSettingsMutation()
  const settings = settingsQuery.data

  const [minWorkMinutes, setMinWorkMinutes] = useState(360)
  const [deductMinutes, setDeductMinutes] = useState(30)
  const [windowStart, setWindowStart] = useState('12:00')
  const [windowEnd, setWindowEnd] = useState('12:30')
  // Gilt für Anlegen, Ändern und Beenden: frühere Tage behalten die alte Regel.
  const [validFrom, setValidFrom] = useState(todayIsoDate())
  const [error, setError] = useState<string | null>(null)

  const rules = rulesQuery.data ?? []
  const staffel = rules.filter((rule) => rule.kind !== 'FIXED_WINDOW')
  const windows = rules.filter((rule) => rule.kind === 'FIXED_WINDOW')

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

  async function handleCreateStaffel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await run(async () => {
      await createRule.mutateAsync({ kind: 'LEGAL', min_work_minutes: minWorkMinutes, deduct_minutes: deductMinutes, valid_from: validFrom })
      setMinWorkMinutes(360)
      setDeductMinutes(30)
    })
  }

  async function handleCreateWindow(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await run(() => createRule.mutateAsync({ kind: 'FIXED_WINDOW', start_time: windowStart, end_time: windowEnd, valid_from: validFrom }))
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Pausenregeln</h1>
        <p className="text-sm text-slate-500">
          Wie viel Pause von der Anwesenheit abgezogen wird – für alle Mitarbeiter. Je Mitarbeiter abweichend: im
          Arbeitszeitmodell unter „Pause“ (bzw. in der Schichtvorlage). Änderungen gelten ab dem gewählten Stichtag; Tage
          davor (und abgeschlossene Monate) rechnen weiter mit den bisherigen Regeln.
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
            Ab wie vielen Arbeitsminuten mindestens wie viel Pause. Gestempelte Pausen zählen mit, nur was fehlt, wird abgezogen
            bzw. – wenn beim Mitarbeiter eingeschaltet – automatisch gestempelt. Strengere Werte des Betriebs (z. B. 30 Min. schon
            ab 4 Std.) einfach als weitere Zeile.
          </p>
        </div>
        {settings && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={settings.legal_break_minimum}
              onChange={(e) => void run(() => updateSettings.mutateAsync({ legal_break_minimum: e.target.checked }))}
            />
            <span>
              Gesetzliche Mindestpause nicht unterschreiten (§ 4 ArbZG: mehr als 6 Std. → 30 Min., mehr als 9 Std. → 45 Min.)
              <span className="block text-xs text-slate-500">
                Aus nur bei abweichender Regelung, z. B. Tarifvertrag nach § 7 ArbZG – dann lässt sich die Staffel frei ändern.
              </span>
            </span>
          </label>
        )}
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
              {staffel.map((rule) => (
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
              {staffel.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-slate-500">
                    Noch keine Pausenregel angelegt.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
        <form className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleCreateStaffel}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="min_work_minutes">Ab Arbeitsminuten</Label>
            <Input id="min_work_minutes" type="number" min={0} className="w-32" value={minWorkMinutes} onChange={(e) => setMinWorkMinutes(Number(e.target.value) || 0)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="deduct_minutes">Pausenabzug (Minuten)</Label>
            <Input id="deduct_minutes" type="number" min={0} className="w-32" value={deductMinutes} onChange={(e) => setDeductMinutes(Number(e.target.value) || 0)} />
          </div>
          <Button type="submit" className="h-auto min-h-9 whitespace-normal py-1.5" disabled={createRule.isPending}>
            <Plus className="h-4 w-4 shrink-0" />
            Regel hinzufügen (ab {formatDate(validFrom)})
          </Button>
        </form>
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-medium text-slate-900">Feste Pausenzeiten</h2>
          <p className="text-sm text-slate-500">
            Z. B. 12:00–12:30: abgezogen, soweit der Mitarbeiter in dieser Zeit da war – auch ohne Pausenstempelung. Gestempelte
            Pausen in dieser Zeit zählen nicht doppelt; die Pausenstaffel gilt zusätzlich als Mindestwert.
          </p>
        </div>
        {windows.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pausenzeit</TableHead>
                <TableHead>Gültig</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {windows.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>
                    <div className="flex items-center gap-2 text-sm">
                      <TimeCell label="Pause von" value={rule.start_time} onCommit={(value) => update(rule, { start_time: value })} />
                      bis
                      <TimeCell label="Pause bis" value={rule.end_time} onCommit={(value) => update(rule, { end_time: value })} />
                    </div>
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
        <form className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleCreateWindow}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="window_start">Pause von</Label>
            <Input id="window_start" type="time" className="w-32" value={windowStart} onChange={(e) => setWindowStart(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="window_end">Pause bis</Label>
            <Input id="window_end" type="time" className="w-32" value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} />
          </div>
          <Button
            type="submit"
            className="h-auto min-h-9 whitespace-normal py-1.5"
            disabled={createRule.isPending || !(windowStart && windowEnd && windowStart < windowEnd)}
          >
            <Plus className="h-4 w-4 shrink-0" />
            Pausenzeit hinzufügen (ab {formatDate(validFrom)})
          </Button>
        </form>
      </section>

      {settings && (
        <section className="flex flex-col gap-3">
          <h2 className="font-medium text-slate-900">Berechnung</h2>
          <DatedSwitch
            label="Pausen genau nach § 4 ArbZG rechnen"
            hint="Die Pausenpflicht richtet sich nach der Arbeitszeit ohne Pausen, und gestempelte Pausen zählen erst ab 15 Minuten. Bisher: nach Anwesenheit, jede gestempelte Pause zählt."
            from={settings.break_precise_from}
            onEnable={(day) => run(() => updateSettings.mutateAsync({ break_precise_from: day }))}
            onDisable={() => run(() => updateSettings.mutateAsync({ clear_break_precise: true }))}
          />
          <DatedSwitch
            label="Pausenabzug höchstens bis zur Schwelle"
            hint="Wer z. B. 6:10 Std. ohne Pause arbeitet, behält 6:00 Std. statt 5:40 Std. – der Abzug drückt die Arbeitszeit nie unter die Schwelle der Staffel."
            from={settings.break_capped_from}
            onEnable={(day) => run(() => updateSettings.mutateAsync({ break_capped_from: day }))}
            onDisable={() => run(() => updateSettings.mutateAsync({ clear_break_capped: true }))}
          />
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={settings.default_auto_break}
              onChange={(e) => void run(() => updateSettings.mutateAsync({ default_auto_break: e.target.checked }))}
            />
            <span>
              Pausen automatisch stempeln – Standard für neue Mitarbeiter
              <span className="block text-xs text-slate-500">
                Die fehlende Pause wird beim Ausstempeln als Buchung eingetragen (je Mitarbeiter im Mitarbeiter-Dialog
                änderbar). Abgezogen wird sie in jedem Fall.
              </span>
            </span>
          </label>
        </section>
      )}
    </div>
  )
}

/** Schalter mit „gilt ab“: an = ab dem gewählten Tag, aus = wieder wie bisher (nicht in abgeschlossenen Monaten). */
function DatedSwitch({
  label,
  hint,
  from,
  onEnable,
  onDisable,
}: {
  label: string
  hint: string
  from: string | null | undefined
  onEnable: (day: string) => Promise<void> | void
  onDisable: () => Promise<void> | void
}) {
  const [day, setDay] = useState(from ?? todayIsoDate())
  useEffect(() => setDay(from ?? todayIsoDate()), [from])
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-1"
          checked={Boolean(from)}
          onChange={(e) => void (e.target.checked ? onEnable(day) : onDisable())}
        />
        <span>
          {label}
          {from ? ` – gilt ab ${formatDate(from)}` : ''}
          <span className="block text-xs text-slate-500">{hint}</span>
        </span>
      </label>
      {!from && (
        <div className="flex items-center gap-2 pl-6">
          <span className="text-slate-500">gilt ab</span>
          <Input type="date" aria-label={`${label} gilt ab`} className="w-44" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
        </div>
      )}
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
