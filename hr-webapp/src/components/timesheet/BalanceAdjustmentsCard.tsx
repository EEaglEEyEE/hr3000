import { useState, type FormEvent } from 'react'
import { Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  useBalanceAdjustmentsQuery,
  useCreateBalanceAdjustmentMutation,
  useDeleteBalanceAdjustmentMutation,
  useSetBalanceMutation,
  type BalanceAdjustment,
} from '../../api/queries/balanceAdjustments'
import { formatDate, formatMinutesAsHours, todayIsoDate } from '../../lib/format'
import { Button } from '../ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

const KIND_LABELS: Record<BalanceAdjustment['kind'], string> = {
  OPENING_BALANCE: 'Anfangskontostand',
  PAYOUT: 'Auszahlung',
  CORRECTION: 'Anpassung',
}

/** Buchungsarten am Überstundenkonto. */
type Action = 'ADJUST' | 'SET' | 'PAYOUT' | 'OPENING'
const ACTION_LABELS: Record<Action, string> = {
  ADJUST: 'Kontostand anpassen (+/−)',
  SET: 'Neuen Kontostand festlegen',
  PAYOUT: 'Überstunden auszahlen',
  OPENING: 'Anfangskontostand (Altsystem/Vorjahr)',
}

/** "8:30" oder "8,5" -> Minuten. */
function parseHours(value: string): number | null {
  const text = value.trim()
  const match = /^(\d{1,4}):([0-5]\d)$/.exec(text)
  if (match) return Number(match[1]) * 60 + Number(match[2])
  const hours = Number(text.replace(',', '.'))
  return Number.isFinite(hours) && hours > 0 ? Math.round(hours * 60) : null
}

export function BalanceAdjustmentsCard({ employeeId, canEdit }: { employeeId: number; canEdit: boolean }) {
  const query = useBalanceAdjustmentsQuery(employeeId)
  const create = useCreateBalanceAdjustmentMutation(employeeId)
  const remove = useDeleteBalanceAdjustmentMutation(employeeId)
  const setBalance = useSetBalanceMutation(employeeId)
  const [action, setAction] = useState<Action>('ADJUST')
  const [factor, setFactor] = useState('1')
  const [direction, setDirection] = useState<'plus' | 'minus'>('plus')
  const [hours, setHours] = useState('')
  const [date, setDate] = useState(todayIsoDate())
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const adjustments = query.data ?? []
  if (!canEdit && adjustments.length === 0) return null

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const minutes = parseHours(hours)
    if (minutes === null) {
      setError('Bitte Stunden als „7,5“ oder „7:30“ angeben.')
      return
    }
    const signed = action === 'PAYOUT' || direction === 'minus' ? -minutes : minutes
    const factorValue = Number(factor.replace(',', '.'))
    if (action === 'PAYOUT' && !(factorValue >= 1 && factorValue <= 3)) {
      setError('Der Faktor liegt zwischen 1 und 3 (z. B. 1,5).')
      return
    }
    try {
      if (action === 'SET') {
        await setBalance.mutateAsync({ effective_date: date, balance_minutes: signed, note: note.trim() })
      } else {
        const kind: BalanceAdjustment['kind'] =
          action === 'PAYOUT' ? 'PAYOUT' : action === 'OPENING' ? 'OPENING_BALANCE' : 'CORRECTION'
        await create.mutateAsync({
          effective_date: date,
          minutes: signed,
          kind,
          note: note.trim(),
          payout_factor: action === 'PAYOUT' && factorValue !== 1 ? factorValue : null,
        })
      }
      setHours('')
      setNote('')
      setFactor('1')
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Datum, Stunden und eine Begründung angeben.')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Korrekturbuchungen Überstundenkonto</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {adjustments.length > 0 && (
          <ul className="divide-y divide-slate-100 text-sm">
            {adjustments.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 py-1.5">
                <span>
                  <span className={a.minutes < 0 ? 'font-medium text-red-600' : 'font-medium text-emerald-700'}>
                    {formatMinutesAsHours(a.minutes)} Std.
                  </span>{' '}
                  {KIND_LABELS[a.kind]}
                  {a.payout_factor != null && ` (Faktor ${String(a.payout_factor).replace('.', ',')})`} zum{' '}
                  {formatDate(a.effective_date)}
                  <span className="block text-xs text-slate-500">{a.note}</span>
                </span>
                {canEdit && (
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Buchung löschen"
                    onClick={() => {
                      if (window.confirm('Buchung löschen?')) {
                        remove.mutate(a.id, { onError: (err) => setError(err instanceof ApiError ? err.message : 'Löschen fehlgeschlagen.') })
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        {canEdit && (
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-1.5">
              <Label>Aktion</Label>
              <Select value={action} onValueChange={(value) => setAction(value as Action)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(ACTION_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="adj_hours">{action === 'SET' ? 'Neuer Kontostand (Stunden)' : 'Stunden'}</Label>
              <div className="flex gap-2">
                {action !== 'PAYOUT' && (
                  <Select value={direction} onValueChange={(value) => setDirection(value as 'plus' | 'minus')}>
                    <SelectTrigger className="w-24">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="plus">+ Plus</SelectItem>
                      <SelectItem value="minus">− Minus</SelectItem>
                    </SelectContent>
                  </Select>
                )}
                <Input id="adj_hours" required placeholder="z. B. 12,5 oder 12:30" value={hours} onChange={(e) => setHours(e.target.value)} />
              </div>
              {action === 'SET' && (
                <p className="text-xs text-slate-500">Gebucht wird die Differenz zum Stand am Ende des gewählten Tages.</p>
              )}
            </div>
            {action === 'PAYOUT' && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="adj_factor">Faktor</Label>
                <Input id="adj_factor" inputMode="decimal" className="w-24" value={factor} onChange={(e) => setFactor(e.target.value)} />
                <p className="text-xs text-slate-500">
                  z. B. 1,5 für 50 % Zuschlag. Das Konto sinkt um die Stunden; im Lohn-Export stehen sie zusätzlich gewichtet.
                </p>
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="adj_date">Buchungsdatum</Label>
              <Input id="adj_date" type="date" required max={todayIsoDate()} value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="adj_note">Begründung</Label>
              <Input id="adj_note" required minLength={3} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            {error && <p className="text-sm text-red-600 sm:col-span-2">{error}</p>}
            <div className="sm:col-span-2">
              <Button type="submit" disabled={create.isPending || setBalance.isPending}>
                Buchen
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
