import { useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { useMyAttributesQuery } from '../../api/queries/attributes'
import {
  useChangeRequestsQuery,
  useDecideChangeRequestMutation,
  useMyChangeRequestsQuery,
  useProposeChangeMutation,
  type ChangeRequest,
} from '../../api/queries/changeRequests'
import { useOwnPersonalDataQuery } from '../../api/queries/personalData'
import { useAuth } from '../../auth/AuthContext'
import { formatDateTime } from '../../lib/format'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

const PERSONAL_FIELDS: { key: string; label: string }[] = [
  { key: 'private_email', label: 'Private E-Mail' },
  { key: 'phone', label: 'Telefon' },
  { key: 'street', label: 'Straße und Hausnummer' },
  { key: 'zip_code', label: 'PLZ' },
  { key: 'city', label: 'Ort' },
  { key: 'country', label: 'Land' },
  { key: 'iban', label: 'IBAN' },
  { key: 'bic', label: 'BIC' },
  { key: 'account_holder', label: 'Kontoinhaber' },
  { key: 'tax_id', label: 'Steuer-ID' },
  { key: 'health_insurance', label: 'Krankenkasse' },
]
const STATUS_LABELS: Record<ChangeRequest['status'], string> = { PENDING: 'offen', APPROVED: 'übernommen', REJECTED: 'abgelehnt' }

function ItemsTable({ request }: { request: ChangeRequest }) {
  return (
    <table className="text-sm">
      <tbody>
        {request.items.map((item) => (
          <tr key={item.field}>
            <td className="pr-4 text-slate-500">{item.label}</td>
            <td className="pr-2 text-slate-400 line-through">{item.old ?? '–'}</td>
            <td className="text-slate-900">{item.new ?? 'leer'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** „Mein Bereich“ → „Meine Daten“: Änderung vorschlagen und eigene Vorschläge. */
export function ProposeChange() {
  const [open, setOpen] = useState(false)
  const mine = useMyChangeRequestsQuery().data ?? []
  return (
    <div className="flex flex-col gap-3">
      <Button variant="outline" className="self-start" onClick={() => setOpen(true)}>
        Änderung vorschlagen
      </Button>
      {mine.length > 0 && (
        <ul className="flex flex-col gap-2">
          {mine.map((request) => (
            <li key={request.id} className="rounded-md border border-slate-200 p-2 text-sm">
              <span className="text-xs text-slate-500">
                {formatDateTime(request.created_at)} · {STATUS_LABELS[request.status]}
                {request.decision_note && ` · ${request.decision_note}`}
              </span>
              <ItemsTable request={request} />
            </li>
          ))}
        </ul>
      )}
      <ProposeDialog open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

function ProposeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const personal = (useOwnPersonalDataQuery().data ?? {}) as Record<string, unknown>
  const attributes = useMyAttributesQuery().data
  const propose = useProposeChangeMutation()
  const [form, setForm] = useState<Record<string, string>>({})
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const editable = (attributes?.sections ?? []).filter((section) => section.employee_access === 'EDIT')
  const currentAttr = new Map((attributes?.values ?? []).map((value) => [value.attribute_id, value.value ?? '']))

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const personalChanges: Record<string, string | null> = {}
    const attributeChanges: Record<string, string | null> = {}
    for (const [key, value] of Object.entries(form)) {
      if (key.startsWith('attr:')) attributeChanges[key.slice(5)] = value.trim() || null
      else personalChanges[key] = value.trim() || null
    }
    propose.mutate(
      { personal: personalChanges, attributes: attributeChanges, note: note || null },
      {
        onSuccess: () => {
          setForm({})
          setNote('')
          onClose()
        },
        onError: (err) => setError(err instanceof ApiError ? err.message : 'Bitte die Eingaben prüfen (z. B. IBAN).'),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Änderung vorschlagen</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
          <p className="text-sm text-slate-600">Nur geänderte Felder werden übermittelt; die Personalabteilung übernimmt sie.</p>
          {PERSONAL_FIELDS.map((field) => (
            <div key={field.key} className="flex flex-col gap-1">
              <Label htmlFor={`cr-${field.key}`}>{field.label}</Label>
              <Input
                id={`cr-${field.key}`}
                value={form[field.key] ?? String(personal[field.key] ?? '')}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
              />
            </div>
          ))}
          {editable.flatMap((section) =>
            section.attributes.map((attribute) => (
              <div key={attribute.id} className="flex flex-col gap-1">
                <Label htmlFor={`cr-attr-${attribute.id}`}>{attribute.label}</Label>
                {attribute.field_type === 'SELECT' ? (
                  <select
                    id={`cr-attr-${attribute.id}`}
                    className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
                    value={form[`attr:${attribute.id}`] ?? currentAttr.get(attribute.id) ?? ''}
                    onChange={(e) => setForm({ ...form, [`attr:${attribute.id}`]: e.target.value })}
                  >
                    <option value="">–</option>
                    {attribute.options.map((option) => (
                      <option key={option}>{option}</option>
                    ))}
                  </select>
                ) : (
                  <Input
                    id={`cr-attr-${attribute.id}`}
                    type={attribute.field_type === 'DATE' ? 'date' : 'text'}
                    value={form[`attr:${attribute.id}`] ?? currentAttr.get(attribute.id) ?? ''}
                    onChange={(e) => setForm({ ...form, [`attr:${attribute.id}`]: e.target.value })}
                  />
                )}
              </div>
            )),
          )}
          <div className="flex flex-col gap-1">
            <Label htmlFor="cr-note">Hinweis (optional)</Label>
            <Input id="cr-note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={propose.isPending || Object.keys(form).length === 0}>
              Vorschlag senden
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** „Zu klären“ → „Datenänderungen“: Vorschläge übernehmen oder ablehnen. */
export function PendingChangeRequests() {
  const { canPayroll } = useAuth()
  const query = useChangeRequestsQuery()
  const decide = useDecideChangeRequestMutation()
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [error, setError] = useState<string | null>(null)
  const requests = query.data ?? []
  if (query.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (requests.length === 0) return <p className="text-sm text-slate-500">Keine offenen Datenänderungen.</p>
  return (
    <div className="flex flex-col gap-3">
      {error && <p className="text-sm text-red-600">{error}</p>}
      {requests.map((request) => {
        const blocked = request.contains_payroll && !canPayroll
        return (
          <div key={request.id} className="flex flex-col gap-2 rounded-md border border-slate-200 p-3">
            <div className="text-sm font-medium text-slate-900">
              {request.employee_name}
              <span className="ml-2 text-xs font-normal text-slate-500">{formatDateTime(request.created_at)}</span>
            </div>
            {request.note && <p className="text-sm text-slate-600">„{request.note}“</p>}
            <ItemsTable request={request} />
            {blocked ? (
              <p className="text-xs text-slate-500">Enthält Bank, Steuer oder Sozialversicherung – entscheidet jemand mit „Vergütung & Lohn-Export“.</p>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  className="w-64"
                  placeholder="Hinweis (optional)"
                  aria-label={`Hinweis zu ${request.employee_name}`}
                  value={notes[request.id] ?? ''}
                  onChange={(e) => setNotes({ ...notes, [request.id]: e.target.value })}
                />
                {[true, false].map((approve) => (
                  <Button
                    key={String(approve)}
                    size="sm"
                    variant={approve ? 'default' : 'outline'}
                    disabled={decide.isPending}
                    onClick={() =>
                      decide.mutate(
                        { id: request.id, approve, note: notes[request.id] },
                        { onError: (err) => setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.') },
                      )
                    }
                  >
                    {approve ? 'Übernehmen' : 'Ablehnen'}
                  </Button>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
