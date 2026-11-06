import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/client'
import {
  useCorrectionRequestsQuery,
  useCreateCorrectionRequestMutation,
  useDecideCorrectionRequestMutation,
  type CorrectionRequest,
  type CorrectionRequestCreate,
} from '../../api/queries/correctionRequests'
import { formatDate, todayIsoDate } from '../../lib/format'
import { PUNCH_TYPE_LABELS } from '../../lib/labels'
import { Badge, type BadgeProps } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

type Item = CorrectionRequestCreate['items'][number]
type PunchType = Item['punch_type']

const STATUS_LABELS: Record<CorrectionRequest['status'], string> = {
  PENDING: 'Offen',
  APPROVED: 'Übernommen',
  REJECTED: 'Abgelehnt',
}

const STATUS_VARIANT: Record<CorrectionRequest['status'], BadgeProps['variant']> = {
  PENDING: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
}

function describeItems(items: Item[]): string {
  return items.map((i) => `${PUNCH_TYPE_LABELS[i.punch_type]} ${i.time}${i.next_day ? ' (Folgetag)' : ''}`).join(', ')
}

/** Mein Bereich: fehlende/falsche Stempelung melden – HR bestätigt, erst dann ändern sich die Zeiten. */
export function CorrectionRequestSelfCard() {
  const requestsQuery = useCorrectionRequestsQuery()
  const create = useCreateCorrectionRequestMutation()
  const [open, setOpen] = useState(false)
  const [workDate, setWorkDate] = useState(todayIsoDate())
  const [items, setItems] = useState<Item[]>([{ punch_type: 'GO', time: '17:00', next_day: false }])
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  function updateItem(index: number, patch: Partial<Item>) {
    setItems((current) => current.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await create.mutateAsync({ work_date: workDate, items, reason: reason.trim() })
      setMessage('Antrag gestellt – HR prüft ihn und übernimmt die Zeiten.')
      setOpen(false)
      setReason('')
      setItems([{ punch_type: 'GO', time: '17:00', next_day: false }])
    } catch (err) {
      setError(
        err instanceof ApiError && err.status !== 422
          ? err.message
          : 'Bitte Eingaben prüfen (Uhrzeit HH:MM, Begründung).',
      )
    }
  }

  const requests = requestsQuery.data ?? []

  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-slate-800">Korrektur beantragen</p>
          <p className="text-sm text-slate-500">Stempelung vergessen? Melde die richtigen Zeiten, HR bestätigt sie.</p>
        </div>
        {!open && (
          <Button
            size="sm"
            onClick={() => {
              setOpen(true)
              setMessage(null)
            }}
          >
            <Plus className="h-4 w-4" />
            Antrag stellen
          </Button>
        )}
      </div>
      {message && <p className="text-sm text-emerald-700">{message}</p>}

      {open && (
        <form className="flex flex-col gap-3 rounded-md bg-slate-50 p-3" onSubmit={handleSubmit}>
          <label className="flex flex-col gap-1 text-sm">
            Tag
            <Input
              type="date"
              className="w-44"
              max={todayIsoDate()}
              value={workDate}
              onChange={(e) => setWorkDate(e.target.value)}
            />
          </label>
          <div className="flex flex-col gap-2">
            {items.map((item, index) => (
              <div key={index} className="flex flex-wrap items-center gap-2">
                <Select
                  value={item.punch_type}
                  onValueChange={(value) => updateItem(index, { punch_type: value as PunchType })}
                >
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(PUNCH_TYPE_LABELS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  type="time"
                  className="w-28"
                  value={item.time}
                  onChange={(e) => updateItem(index, { time: e.target.value })}
                />
                <label className="flex items-center gap-1.5 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={item.next_day ?? false}
                    onChange={(e) => updateItem(index, { next_day: e.target.checked })}
                  />
                  Folgetag (Nachtschicht)
                </label>
                {items.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => setItems((c) => c.filter((_, i) => i !== index))}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                )}
              </div>
            ))}
            {items.length < 6 && (
              <button
                type="button"
                className="self-start text-xs text-sky-700 underline"
                onClick={() => setItems((c) => [...c, { punch_type: 'COME', time: '08:00', next_day: false }])}
              >
                weitere Stempelung hinzufügen
              </button>
            )}
          </div>
          <label className="flex flex-col gap-1 text-sm">
            Begründung
            <Input
              maxLength={500}
              placeholder="z. B. Ausstempeln vergessen"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
              Abbrechen
            </Button>
            <Button type="submit" size="sm" disabled={create.isPending || reason.trim().length < 3}>
              Antrag senden
            </Button>
          </div>
        </form>
      )}

      {requests.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tag</TableHead>
              <TableHead>Stempelungen</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {requests.slice(0, 10).map((request) => (
              <TableRow key={request.id}>
                <TableCell>{formatDate(request.work_date)}</TableCell>
                <TableCell className="text-sm">
                  {describeItems(request.items)}
                  {request.decision_note && <div className="text-xs text-slate-500">HR: {request.decision_note}</div>}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[request.status]}>{STATUS_LABELS[request.status]}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

/** Zu klären → „Korrekturanträge“: offene Korrekturanträge übernehmen oder ablehnen (nur Admin/HR). */
export function PendingCorrectionRequests() {
  const navigate = useNavigate()
  const requestsQuery = useCorrectionRequestsQuery('PENDING')
  const decide = useDecideCorrectionRequestMutation()
  const [error, setError] = useState<string | null>(null)

  async function handleDecide(request: CorrectionRequest, approve: boolean) {
    setError(null)
    const note = approve ? undefined : (window.prompt('Begründung für die Ablehnung (optional):') ?? undefined)
    try {
      await decide.mutateAsync({ requestId: request.id, approve, note })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Entscheidung fehlgeschlagen.')
    }
  }

  const requests = requestsQuery.data ?? []
  if (requestsQuery.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (requests.length === 0) return <p className="text-sm text-slate-500">Keine offenen Korrekturanträge.</p>

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-slate-500">
        Von Mitarbeitern beantragte Korrekturen ihrer Stempelungen. „Übernehmen“ trägt sie ein.
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mitarbeiter</TableHead>
            <TableHead>Tag</TableHead>
            <TableHead>Beantragt</TableHead>
            <TableHead>Begründung</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {requests.map((request) => (
            <TableRow key={request.id}>
              <TableCell>
                <button
                  type="button"
                  className="text-sky-700 hover:underline"
                  onClick={() => navigate(`/employees/${request.employee_id}`)}
                >
                  {request.employee_name}
                </button>
              </TableCell>
              <TableCell>{formatDate(request.work_date)}</TableCell>
              <TableCell className="text-sm">{describeItems(request.items)}</TableCell>
              <TableCell className="text-sm text-slate-600">{request.reason}</TableCell>
              <TableCell className="flex justify-end gap-2">
                <Button size="sm" disabled={decide.isPending} onClick={() => void handleDecide(request, true)}>
                  Übernehmen
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={decide.isPending}
                  onClick={() => void handleDecide(request, false)}
                >
                  Ablehnen
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
