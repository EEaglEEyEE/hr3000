import { useState, type FormEvent } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  useCreateDefaultSurchargeRulesMutation,
  useCreateSurchargeRuleMutation,
  useDeleteSurchargeRuleMutation,
  useSurchargeRulesQuery,
  useToggleSurchargeRuleMutation,
  useUpdateSurchargeRuleMutation,
  type SurchargeRule,
} from '../api/queries/surcharges'
import { formatDate, todayIsoDate } from '../lib/format'
import { Button } from '../components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { SURCHARGE_KIND_LABELS } from '../lib/labels'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function describe(rule: SurchargeRule): string {
  if (rule.kind === 'NIGHT' || rule.kind === 'CUSTOM') {
    const days = rule.weekdays.length === 7 ? 'täglich' : rule.weekdays.map((d) => WEEKDAYS[d]).join(', ')
    return `${rule.start_time?.slice(0, 5)}–${rule.end_time?.slice(0, 5)} Uhr, ${days}`
  }
  return '–'
}

function validity(rule: SurchargeRule): string {
  if (!rule.valid_from && !rule.valid_to) return 'immer'
  if (rule.valid_from && rule.valid_to) return `${formatDate(rule.valid_from)} – ${formatDate(rule.valid_to)}`
  return rule.valid_from ? `ab ${formatDate(rule.valid_from)}` : `bis ${formatDate(rule.valid_to!)}`
}

export function SurchargeRulesPage() {
  const [showHistory, setShowHistory] = useState(false)
  const rulesQuery = useSurchargeRulesQuery({ includeHistory: showHistory })
  const [editing, setEditing] = useState<SurchargeRule | null>(null)
  const createDefaults = useCreateDefaultSurchargeRulesMutation()
  const toggle = useToggleSurchargeRuleMutation()
  const remove = useDeleteSurchargeRuleMutation()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setMessage(null)
    try {
      await action()
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Aktion fehlgeschlagen.')
    }
  }

  const rules = rulesQuery.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Zuschläge</h1>
        <div className="flex gap-2">
          {rules.length === 0 && (
            <Button variant="outline" onClick={() => void run(() => createDefaults.mutateAsync())}>
              Standardregeln anlegen
            </Button>
          )}
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Neue Regel
          </Button>
        </div>
      </div>
      <p className="text-sm text-slate-500">
        Die Regeln werten die tatsächlich gearbeitete Zeit aus (Stunden je Regel) und erscheinen im Monatsnachweis, im
        Lohn-Export und in den Auswertungen. Regeln derselben „Gruppe“ werden nicht addiert – je Minute zählt nur der höchste
        Satz (z. B. Sonntag + Feiertag). Die steuerliche bzw. tarifliche Bewertung bleibt bei der Lohnbuchhaltung; die
        Standardregeln sind nur ein Vorschlag (orientiert an § 3b EStG) und müssen geprüft werden. Änderungen an Satz,
        Zeitfenster oder Wochentagen gelten ab „Änderung gilt ab“ – zurückliegende Monate rechnen mit der bisherigen Fassung.
      </p>
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} />
        Frühere Fassungen anzeigen
      </label>
      {message && <p className="text-sm text-red-600">{message}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Art</TableHead>
            <TableHead>Satz</TableHead>
            <TableHead>Zeitfenster</TableHead>
            <TableHead>Gruppe</TableHead>
            <TableHead>Gültig</TableHead>
            <TableHead>Aktiv</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rules.map((rule) => (
            <TableRow key={rule.id}>
              <TableCell className="font-medium">{rule.name}</TableCell>
              <TableCell>{SURCHARGE_KIND_LABELS[rule.kind]}</TableCell>
              <TableCell>{rule.percent.toLocaleString('de-DE')} %</TableCell>
              <TableCell>{describe(rule)}</TableCell>
              <TableCell>{rule.exclusive_group ?? '–'}</TableCell>
              <TableCell className={rule.valid_to && rule.valid_to < todayIsoDate() ? 'text-slate-400' : undefined}>
                {validity(rule)}
              </TableCell>
              <TableCell>
                <input
                  type="checkbox"
                  checked={rule.active}
                  onChange={(e) => void run(() => toggle.mutateAsync({ id: rule.id, active: e.target.checked }))}
                />
              </TableCell>
              <TableCell className="whitespace-nowrap">
                {(!rule.valid_to || rule.valid_to >= todayIsoDate()) && (
                  <Button variant="ghost" size="icon" aria-label={`${rule.name} bearbeiten`} onClick={() => setEditing(rule)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`${rule.name} löschen`}
                  onClick={() => {
                    if (window.confirm(`Regel "${rule.name}" (${validity(rule)}) löschen?`)) void run(() => remove.mutateAsync(rule.id))
                  }}
                >
                  <Trash2 className="h-4 w-4 text-red-600" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {rules.length === 0 && !rulesQuery.isLoading && (
            <TableRow>
              <TableCell colSpan={8} className="text-center text-slate-500">
                Noch keine Zuschlagsregeln.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <RuleDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      {editing && <RuleDialog open rule={editing} onOpenChange={(open) => !open && setEditing(null)} />}
    </div>
  )
}

function RuleDialog({
  open,
  onOpenChange,
  rule,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  rule?: SurchargeRule
}) {
  const create = useCreateSurchargeRuleMutation()
  const update = useUpdateSurchargeRuleMutation()
  const [name, setName] = useState(rule?.name ?? '')
  const [kind, setKind] = useState<SurchargeRule['kind']>(rule?.kind ?? 'NIGHT')
  const [percent, setPercent] = useState(rule ? String(rule.percent).replace('.', ',') : '25')
  const [start, setStart] = useState(rule?.start_time?.slice(0, 5) ?? '22:00')
  const [end, setEnd] = useState(rule?.end_time?.slice(0, 5) ?? '06:00')
  const [weekdays, setWeekdays] = useState<number[]>(rule?.weekdays ?? [0, 1, 2, 3, 4, 5, 6])
  const [group, setGroup] = useState(rule?.exclusive_group ?? '')
  // Neue Regel: leer = auch rückwirkend; Änderung: Standard heute (frühere Monate bleiben)
  const [validFrom, setValidFrom] = useState(rule ? todayIsoDate() : '')
  const [error, setError] = useState<string | null>(null)

  const timed = kind === 'NIGHT' || kind === 'CUSTOM'
  const parsedPercent = Number(percent.replace(',', '.'))
  const calculationChanged =
    rule !== undefined &&
    (parsedPercent !== rule.percent ||
      (timed &&
        (`${start}:00` !== rule.start_time ||
          `${end}:00` !== rule.end_time ||
          [...weekdays].sort().join() !== [...rule.weekdays].sort().join())))

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const parsed = Number(percent.replace(',', '.'))
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 500) {
      setError('Bitte einen Prozentsatz zwischen 0 und 500 angeben.')
      return
    }
    try {
      if (rule) {
        await update.mutateAsync({
          id: rule.id,
          payload: {
            name: name.trim(),
            percent: parsed,
            ...(timed ? { start_time: `${start}:00`, end_time: `${end}:00`, weekdays } : {}),
            ...(group.trim() ? { exclusive_group: group.trim() } : {}),
            clear_exclusive_group: !group.trim(),
            ...(calculationChanged && validFrom ? { valid_from: validFrom } : {}),
          },
        })
      } else {
        await create.mutateAsync({
          name: name.trim(),
          kind,
          percent: parsed,
          start_time: timed ? `${start}:00` : null,
          end_time: timed ? `${end}:00` : null,
          weekdays: timed ? weekdays : [0, 1, 2, 3, 4, 5, 6],
          exclusive_group: group.trim() || null,
          active: true,
          valid_from: validFrom || null,
        })
        setName('')
      }
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Angaben prüfen (Gruppe nur Buchstaben, Ziffern, _ und -).')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{rule ? `Zuschlagsregel „${rule.name}“ bearbeiten` : 'Neue Zuschlagsregel'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule_name">Name</Label>
            <Input id="rule_name" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Art</Label>
              <Select value={kind} disabled={rule !== undefined} onValueChange={(value) => setKind(value as SurchargeRule['kind'])}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(SURCHARGE_KIND_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rule_percent">Zuschlag in %</Label>
              <Input id="rule_percent" inputMode="decimal" required value={percent} onChange={(e) => setPercent(e.target.value)} />
            </div>
          </div>
          {timed && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="rule_start">Von</Label>
                  <Input id="rule_start" type="time" required value={start} onChange={(e) => setStart(e.target.value)} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="rule_end">Bis (ggf. nächster Tag)</Label>
                  <Input id="rule_end" type="time" required value={end} onChange={(e) => setEnd(e.target.value)} />
                </div>
              </div>
              <div className="flex flex-wrap gap-3 text-sm">
                {WEEKDAYS.map((label, day) => (
                  <label key={label} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={weekdays.includes(day)}
                      onChange={(e) =>
                        setWeekdays((current) => (e.target.checked ? [...current, day].sort() : current.filter((d) => d !== day)))
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
            </>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule_group">Gruppe (optional, nur der höchste Satz je Gruppe zählt)</Label>
            <Input id="rule_group" maxLength={50} placeholder="z. B. sonn_feiertag" value={group} onChange={(e) => setGroup(e.target.value)} />
          </div>
          {(!rule || calculationChanged) && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rule_valid_from">{rule ? 'Änderung gilt ab' : 'Gilt ab (optional)'}</Label>
              <Input id="rule_valid_from" type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
              <p className="text-xs text-slate-500">
                {rule
                  ? 'Tage davor rechnen weiter mit dem bisherigen Satz bzw. Zeitfenster. Leer = bestehende Fassung rückwirkend korrigieren.'
                  : 'Leer = gilt auch für zurückliegende Zeiträume.'}
              </p>
            </div>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={create.isPending || update.isPending || (timed && weekdays.length === 0)}>
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
