/** Zulagen (je Monat oder je Ist-Stunde) und Einmalzahlungen eines Mitarbeiters – nur für Admins. */
import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  useCreatePayComponentMutation,
  useDeletePayComponentMutation,
  usePayComponentsQuery,
  useUpdatePayComponentMutation,
  type PayComponent,
  type PayComponentCreateRequest,
} from '../../api/queries/employment'
import { usePayComponentTypesQuery } from '../../api/queries/wageTypes'
import { formatDate, todayIsoDate } from '../../lib/format'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

function euro(value: number): string {
  return value.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function describeAmount(component: PayComponent): string {
  if (component.kind === 'ONE_TIME') {
    const value =
      component.percent_of_salary != null
        ? `${String(component.percent_of_salary).replace('.', ',')} % des Monatsgehalts`
        : `${euro(component.amount)} EUR`
    return `${value} ${component.recurs_yearly ? 'jährlich' : 'einmalig'}`
  }
  return `${euro(component.amount)} EUR ${component.unit === 'PER_HOUR' ? 'je Ist-Stunde' : 'je Monat'}`
}

function describeWhen(component: PayComponent): string {
  if (component.kind === 'ONE_TIME') {
    if (!component.pay_date) return ''
    if (!component.recurs_yearly) return `am ${formatDate(component.pay_date)}`
    const end = component.valid_to ? `, bis ${formatDate(component.valid_to)}` : ''
    return `jährlich am ${formatDate(component.pay_date).slice(0, 6)} ab ${component.pay_date.slice(0, 4)}${end}`
  }
  return `ab ${formatDate(component.valid_from!)}${component.valid_to ? ` bis ${formatDate(component.valid_to)}` : ', unbefristet'}`
}

export function PayComponentsSection({ employeeId, canEdit = true }: { employeeId: number; canEdit?: boolean }) {
  const query = usePayComponentsQuery(employeeId, true)
  const updateComponent = useUpdatePayComponentMutation(employeeId)
  const deleteComponent = useDeletePayComponentMutation(employeeId)
  const [dialogKind, setDialogKind] = useState<PayComponent['kind'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Zulage beenden: Zeile mit Datumsfeld
  const [ending, setEnding] = useState<{ id: number; date: string } | null>(null)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Speichern fehlgeschlagen.')
    }
  }

  function endAllowance(componentId: number, date: string) {
    void run(async () => {
      await updateComponent.mutateAsync({ componentId, payload: { valid_to: date, clear_valid_to: false } })
      setEnding(null)
    })
  }

  function remove(component: PayComponent) {
    if (!window.confirm(`„${component.name}“ wirklich löschen?`)) return
    void run(() => deleteComponent.mutateAsync(component.id))
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Zulagen &amp; Einmalzahlungen</h2>
          <p className="text-sm text-slate-500">
            Erscheinen im Lohn-Export, wenn ein Admin ihn zieht. Zulagen je Monat zählen in angebrochenen Monaten anteilig
            nach Kalendertagen, Zulagen je Stunde mit den Ist-Stunden.
          </p>
        </div>
        {canEdit ? (
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setDialogKind('ALLOWANCE')}>
              <Plus className="h-4 w-4" />
              Neue Zulage
            </Button>
            <Button variant="outline" onClick={() => setDialogKind('ONE_TIME')}>
              <Plus className="h-4 w-4" />
              Neue Einmalzahlung
            </Button>
          </div>
        ) : (
          <span className="text-sm text-slate-500">Nur Ansicht – deine Rolle darf hier nichts ändern.</span>
        )}
      </div>
      {query.isLoading && <p className="text-slate-500">Lädt…</p>}
      {query.isError && <p className="text-red-600">Zulagen konnten nicht geladen werden.</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Bezeichnung</TableHead>
            <TableHead>Betrag</TableHead>
            <TableHead>Zeitraum</TableHead>
            <TableHead>Lohnart</TableHead>
            <TableHead>Notiz</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {query.data?.map((component) => (
            <TableRow key={component.id}>
              <TableCell className="font-medium">{component.name}</TableCell>
              <TableCell>{describeAmount(component)}</TableCell>
              <TableCell>{describeWhen(component)}</TableCell>
              <TableCell>{component.wage_type ?? '–'}</TableCell>
              <TableCell>{component.note ?? '–'}</TableCell>
              <TableCell className="whitespace-nowrap text-right">
                {canEdit && (component.kind === 'ALLOWANCE' || component.recurs_yearly) && !component.valid_to && ending?.id !== component.id && (
                  <Button variant="ghost" size="sm" onClick={() => setEnding({ id: component.id, date: todayIsoDate() })}>
                    Beenden
                  </Button>
                )}
                {canEdit && ending?.id === component.id && (
                  <span className="inline-flex items-center gap-1">
                    <Input
                      type="date"
                      aria-label="Gültig bis"
                      className="w-40"
                      value={ending.date}
                      onChange={(e) => setEnding({ id: component.id, date: e.target.value })}
                    />
                    <Button size="sm" disabled={!ending.date} onClick={() => endAllowance(component.id, ending.date)}>
                      OK
                    </Button>
                  </span>
                )}
                {canEdit && (
                  <Button variant="ghost" size="icon" title="Löschen" onClick={() => remove(component)}>
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
          {query.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-slate-500">
                Keine Zulagen oder Einmalzahlungen hinterlegt.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {dialogKind && <PayComponentDialog kind={dialogKind} employeeId={employeeId} onClose={() => setDialogKind(null)} />}
    </section>
  )
}

function PayComponentDialog({
  kind,
  employeeId,
  onClose,
}: {
  kind: PayComponent['kind']
  employeeId: number
  onClose: () => void
}) {
  const create = useCreatePayComponentMutation(employeeId)
  // Arten aus dem Katalog („Lohnarten“): passende Art wählen oder eine neue anlegen
  const typesQuery = usePayComponentTypesQuery()
  const allowance = kind === 'ALLOWANCE'
  const [name, setName] = useState(allowance ? '' : 'Weihnachtsgeld')
  const [amount, setAmount] = useState('')
  // Einmalzahlung: Betrag in EUR oder % des Monatsgehalts; „jährlich“ wiederholen
  const [mode, setMode] = useState<'EUR' | 'PERCENT'>('EUR')
  const [yearly, setYearly] = useState(false)
  const [unit, setUnit] = useState<'PER_MONTH' | 'PER_HOUR'>('PER_MONTH')
  const [from, setFrom] = useState(todayIsoDate())
  const [to, setTo] = useState('')
  const [wageType, setWageType] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const types = (typesQuery.data ?? []).filter((t) => t.kind === kind)
  const existing = types.find((t) => t.name.toLowerCase() === name.trim().toLowerCase())

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (existing && !existing.active) {
      setError(`Die Art „${existing.name}“ ist inaktiv – unter „Lohnarten“ wieder aktivieren oder eine andere wählen.`)
      return
    }
    const parsed = Number(amount.replace(',', '.'))
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError(mode === 'PERCENT' && !allowance ? 'Bitte einen Prozentsatz größer 0 angeben.' : 'Bitte einen Betrag größer 0 angeben.')
      return
    }
    const percent = !allowance && mode === 'PERCENT'
    const payload: PayComponentCreateRequest = {
      kind,
      ...(existing ? { type_id: existing.id } : { type_name: name.trim(), wage_type: wageType.trim() || null }),
      ...(percent ? { percent_of_salary: parsed } : { amount: parsed }),
      recurs_yearly: !allowance && yearly,
      note: note.trim() || null,
      ...(allowance ? { unit, valid_from: from, valid_to: to || null } : { pay_date: from }),
    }
    try {
      await create.mutateAsync(payload)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Angaben prüfen (Betrag mit höchstens 2 Nachkommastellen, Lohnart nur Ziffern).')
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{allowance ? 'Neue Zulage' : 'Neue Einmalzahlung'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pc_name">Bezeichnung</Label>
            <Input
              id="pc_name"
              required
              maxLength={100}
              list="pc_types"
              placeholder={allowance ? 'z. B. Fahrtkostenzuschuss' : 'z. B. Weihnachtsgeld'}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <datalist id="pc_types">
              {types
                .filter((t) => t.active)
                .map((t) => (
                  <option key={t.id} value={t.name} />
                ))}
            </datalist>
            <p className="text-xs text-slate-500">
              {existing
                ? `Art aus „Lohnarten“ – Lohnart ${existing.wage_type ?? 'nicht hinterlegt'}.`
                : name.trim()
                  ? 'Neue Art – wird unter „Lohnarten“ angelegt und steht dann bei allen Mitarbeitern zur Auswahl.'
                  : 'Vorhandene Art wählen oder einen neuen Namen eingeben.'}
            </p>
          </div>
          {allowance && (
            <div className="flex flex-wrap gap-2 text-sm">
              {(
                [
                  ['PER_MONTH', 'Je Monat'],
                  ['PER_HOUR', 'Je Stunde (auf den Stundenlohn)'],
                ] as const
              ).map(([value, label]) => (
                <Button
                  key={value}
                  type="button"
                  size="sm"
                  variant={unit === value ? 'default' : 'outline'}
                  aria-pressed={unit === value}
                  onClick={() => setUnit(value)}
                >
                  {label}
                </Button>
              ))}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pc_amount">
                {allowance
                  ? unit === 'PER_HOUR'
                    ? 'Betrag je Stunde (EUR)'
                    : 'Betrag je Monat (EUR)'
                  : mode === 'PERCENT'
                    ? '% des Monatsgehalts'
                    : 'Betrag (EUR)'}
              </Label>
              <Input id="pc_amount" inputMode="decimal" required value={amount} onChange={(e) => setAmount(e.target.value)} />
              {!allowance && (
                <div className="flex flex-col gap-1 text-xs text-slate-600">
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={mode === 'PERCENT'} onChange={(e) => setMode(e.target.checked ? 'PERCENT' : 'EUR')} />
                    in % des Monatsgehalts (z. B. 50 = Urlaubsgeld, 100 = 13. Gehalt)
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={yearly} onChange={(e) => setYearly(e.target.checked)} />
                    jährlich wiederholen (bis „Beenden“)
                  </label>
                </div>
              )}
            </div>
            {!existing && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pc_wage_type">Lohnart (optional)</Label>
                <Input id="pc_wage_type" inputMode="numeric" maxLength={6} value={wageType} onChange={(e) => setWageType(e.target.value)} />
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pc_from">{allowance ? 'Gültig ab' : 'Auszahlung am'}</Label>
              <Input id="pc_from" type="date" required value={from} onChange={(e) => setFrom(e.target.value)} />
            </div>
            {allowance && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pc_to">Gültig bis (optional)</Label>
                <Input id="pc_to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pc_note">Notiz (optional)</Label>
            <Input id="pc_note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
