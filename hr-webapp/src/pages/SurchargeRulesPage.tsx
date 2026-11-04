import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  useCreateDefaultSurchargeRulesMutation,
  useCreateSurchargeRuleMutation,
  useDeleteSurchargeRuleMutation,
  useSurchargeRulesQuery,
  useToggleSurchargeRuleMutation,
  type SurchargeRule,
} from '../api/queries/surcharges'
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

export function SurchargeRulesPage() {
  const rulesQuery = useSurchargeRulesQuery()
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
        Standardregeln sind nur ein Vorschlag (orientiert an § 3b EStG) und müssen geprüft werden.
      </p>
      {message && <p className="text-sm text-red-600">{message}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Art</TableHead>
            <TableHead>Satz</TableHead>
            <TableHead>Zeitfenster</TableHead>
            <TableHead>Gruppe</TableHead>
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
              <TableCell>
                <input
                  type="checkbox"
                  checked={rule.active}
                  onChange={(e) => void run(() => toggle.mutateAsync({ id: rule.id, active: e.target.checked }))}
                />
              </TableCell>
              <TableCell>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => {
                    if (window.confirm(`Regel "${rule.name}" löschen?`)) void run(() => remove.mutateAsync(rule.id))
                  }}
                >
                  <Trash2 className="h-4 w-4 text-red-600" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {rules.length === 0 && !rulesQuery.isLoading && (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-slate-500">
                Noch keine Zuschlagsregeln.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <RuleDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  )
}

function RuleDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const create = useCreateSurchargeRuleMutation()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<SurchargeRule['kind']>('NIGHT')
  const [percent, setPercent] = useState('25')
  const [start, setStart] = useState('22:00')
  const [end, setEnd] = useState('06:00')
  const [weekdays, setWeekdays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6])
  const [group, setGroup] = useState('')
  const [error, setError] = useState<string | null>(null)

  const timed = kind === 'NIGHT' || kind === 'CUSTOM'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const parsed = Number(percent.replace(',', '.'))
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 500) {
      setError('Bitte einen Prozentsatz zwischen 0 und 500 angeben.')
      return
    }
    try {
      await create.mutateAsync({
        name: name.trim(),
        kind,
        percent: parsed,
        start_time: timed ? `${start}:00` : null,
        end_time: timed ? `${end}:00` : null,
        weekdays: timed ? weekdays : [0, 1, 2, 3, 4, 5, 6],
        exclusive_group: group.trim() || null,
        active: true,
      })
      setName('')
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Angaben prüfen (Gruppe nur Buchstaben, Ziffern, _ und -).')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Neue Zuschlagsregel</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule_name">Name</Label>
            <Input id="rule_name" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Art</Label>
              <Select value={kind} onValueChange={(value) => setKind(value as SurchargeRule['kind'])}>
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
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={create.isPending || (timed && weekdays.length === 0)}>
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
