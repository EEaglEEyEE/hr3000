import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Paperclip } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  downloadWhistleAttachment,
  useDeleteWhistleCaseMutation,
  useWhistleCaseQuery,
  useWhistleCasesQuery,
  useWhistleCaseUpdateMutation,
  useWhistleMessageMutation,
  type WhistleCaseDetail,
  type WhistleCaseSummary,
  type WhistleStatus,
} from '../api/queries/whistle'
import { Badge, type BadgeProps } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Label } from '../components/ui/label'
import { formatBytes, formatDate, formatDateTime, TEXTAREA_CLASS } from '../components/whistle/textarea'
import { AUDIT_ACTION_LABELS, WHISTLE_CATEGORY_LABELS, WHISTLE_STATUS_LABELS } from '../lib/labels'
import { cn } from '../lib/utils'

const STATUS_VARIANT: Record<WhistleStatus, BadgeProps['variant']> = {
  RECEIVED: 'warning',
  IN_REVIEW: 'info',
  FEEDBACK_GIVEN: 'violet',
  CLOSED: 'default',
}

function errorText(error: unknown): string | null {
  if (!error) return null
  return error instanceof ApiError && error.status !== 422 ? error.message : 'Bitte die Eingaben prüfen.'
}

/** Meldestelle: Liste und Bearbeitung der Hinweise – nur für benannte Beauftragte (Backend: sonst 404). */
export function WhistleCasesPage() {
  const { caseId } = useParams()
  const id = caseId && /^\d+$/.test(caseId) ? Number(caseId) : null
  return id !== null ? <CaseDetail caseId={id} /> : <CaseList />
}

function Deadline({ date, overdue, done }: { date: string; overdue: boolean; done: boolean }) {
  if (done) return <span className="text-slate-400">erledigt</span>
  return <span className={cn(overdue && 'font-semibold text-red-600')}>{formatDate(date)}{overdue ? ' (überfällig)' : ''}</span>
}

function CaseList() {
  const casesQuery = useWhistleCasesQuery()
  const [filter, setFilter] = useState<'open' | 'closed' | 'all'>('open')

  if (casesQuery.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (casesQuery.isError) {
    return <p className="text-slate-600">Die Hinweise sind nur für benannte Meldestellen-Beauftragte sichtbar.</p>
  }
  const cases = casesQuery.data ?? []
  const shown = cases.filter((c) => filter === 'all' || (filter === 'open' ? c.status !== 'CLOSED' : c.status === 'CLOSED'))
  const dueForDeletion = cases.filter((c) => c.deletion_due).length

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Hinweise</h1>
        <p className="text-sm text-slate-500">
          Interne Meldestelle. Nur die benannten Beauftragten sehen diese Seite; jedes Öffnen wird am Vorgang protokolliert.
        </p>
      </div>
      {dueForDeletion > 0 && (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800" role="status">
          {dueForDeletion === 1 ? '1 abgeschlossener Vorgang ist' : `${dueForDeletion} abgeschlossene Vorgänge sind`} zur Löschung fällig.
        </p>
      )}
      <div className="flex gap-2" role="tablist" aria-label="Filter">
        {(
          [
            ['open', 'Offen'],
            ['closed', 'Abgeschlossen'],
            ['all', 'Alle'],
          ] as const
        ).map(([key, text]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={filter === key}
            onClick={() => setFilter(key)}
            className={cn('rounded-md px-3 py-1.5 text-sm font-medium', filter === key ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100')}
          >
            {text}
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="text-sm text-slate-500">Keine Hinweise.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Vorgang</th>
                <th className="px-3 py-2">Kategorie</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Eingang</th>
                <th className="px-3 py-2">Eingangsbestätigung bis</th>
                <th className="px-3 py-2">Rückmeldung bis</th>
                <th className="px-3 py-2">Löschdatum</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((item) => (
                <CaseRow key={item.id} item={item} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function CaseRow({ item }: { item: WhistleCaseSummary }) {
  const closed = item.status === 'CLOSED'
  return (
    <tr className="border-t border-slate-100">
      <td className="px-3 py-2">
        <Link to={`/hinweise/${item.id}`} className="font-mono font-medium text-sky-700 hover:underline">
          {item.case_number}
        </Link>
        {item.unread && (
          <span className="ml-2 rounded-full bg-red-600 px-1.5 text-[10px] font-semibold text-white" title="Neu">
            neu
          </span>
        )}
      </td>
      <td className="px-3 py-2">{WHISTLE_CATEGORY_LABELS[item.category]}</td>
      <td className="px-3 py-2">
        <Badge variant={STATUS_VARIANT[item.status]}>{WHISTLE_STATUS_LABELS[item.status]}</Badge>
      </td>
      <td className="px-3 py-2">{formatDateTime(item.received_at)}</td>
      <td className="px-3 py-2">
        <Deadline date={item.ack_due} overdue={item.ack_overdue} done={item.acknowledged_at !== null || closed} />
      </td>
      <td className="px-3 py-2">
        <Deadline date={item.feedback_due} overdue={item.feedback_overdue} done={item.feedback_at !== null || closed} />
      </td>
      <td className="px-3 py-2">
        {item.delete_after ? (
          <span className={cn(item.deletion_due && 'font-semibold text-amber-700')}>
            {formatDate(item.delete_after)}
            {item.deletion_due ? ' (fällig)' : ''}
          </span>
        ) : (
          '–'
        )}
      </td>
    </tr>
  )
}

function CaseDetail({ caseId }: { caseId: number }) {
  const caseQuery = useWhistleCaseQuery(caseId)
  if (caseQuery.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (caseQuery.isError || !caseQuery.data) {
    return (
      <div className="flex flex-col gap-2">
        <BackLink />
        <p className="text-slate-600">Dieser Hinweis ist nicht verfügbar.</p>
      </div>
    )
  }
  return <CaseView data={caseQuery.data} />
}

function BackLink() {
  return (
    <Link to="/hinweise" className="flex items-center gap-1 text-sm text-sky-700 hover:underline">
      <ArrowLeft className="h-4 w-4" /> Alle Hinweise
    </Link>
  )
}

function Field({ label, value }: { label: string; value: string | null }) {
  if (!value) return null
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="whitespace-pre-wrap text-sm text-slate-800">{value}</dd>
    </div>
  )
}

function CaseView({ data }: { data: WhistleCaseDetail }) {
  const closed = data.status === 'CLOSED'
  const [downloadError, setDownloadError] = useState<string | null>(null)

  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-lg font-semibold text-slate-900">{data.case_number}</h1>
        <Badge variant={STATUS_VARIANT[data.status]}>{WHISTLE_STATUS_LABELS[data.status]}</Badge>
        <span className="text-sm text-slate-600">{WHISTLE_CATEGORY_LABELS[data.category]}</span>
        <span className="text-sm text-slate-500">{data.anonymous ? 'anonym' : 'mit Kontaktangabe'}</span>
      </div>

      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-4">
          <section className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4" aria-label="Meldung">
            <p className="text-sm font-medium text-slate-800">Meldung vom {formatDateTime(data.received_at)}</p>
            <p className="whitespace-pre-wrap text-sm text-slate-800">{data.description}</p>
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Field label="Zeitpunkt" value={data.occurred_when} />
              <Field label="Ort" value={data.occurred_where} />
              <Field label="Name" value={data.contact_name} />
              <Field label="E-Mail" value={data.contact_email} />
            </dl>
            {data.attachments.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-xs text-slate-500">Anhänge</p>
                {data.attachments.map((file) => (
                  <button
                    key={file.id}
                    type="button"
                    className="flex items-center gap-1 self-start text-sm text-sky-700 hover:underline"
                    onClick={() =>
                      downloadWhistleAttachment(data.id, file.id, file.filename).catch((err: unknown) =>
                        setDownloadError(err instanceof Error ? err.message : 'Der Anhang konnte nicht geladen werden.'),
                      )
                    }
                  >
                    <Paperclip className="h-4 w-4" /> {file.filename} ({formatBytes(file.size_bytes)})
                  </button>
                ))}
                {downloadError && <p className="text-sm text-red-600">{downloadError}</p>}
              </div>
            )}
          </section>

          <Messages data={data} />
          {!closed && <Composer data={data} />}
        </div>

        <div className="flex flex-col gap-4">
          <Deadlines data={data} />
          <StatusForm data={data} />
          <Protocol data={data} />
        </div>
      </div>
    </div>
  )
}

function Messages({ data }: { data: WhistleCaseDetail }) {
  return (
    <section className="flex flex-col gap-2" aria-label="Verlauf">
      <p className="text-sm font-medium text-slate-800">Verlauf</p>
      {data.messages.length === 0 && <p className="text-sm text-slate-500">Noch keine Nachrichten oder Notizen.</p>}
      {data.messages.map((message) => (
        <div
          key={message.id}
          className={cn(
            'rounded-md border p-3 text-sm',
            message.kind === 'REPORTER' && 'border-slate-200 bg-white',
            message.kind === 'OFFICE' && 'ml-6 border-sky-200 bg-sky-50',
            message.kind === 'NOTE' && 'ml-6 border-dashed border-amber-300 bg-amber-50',
          )}
        >
          <p className="mb-1 text-xs text-slate-500">
            {message.kind === 'REPORTER' && 'Meldende Person'}
            {message.kind === 'OFFICE' && `Nachricht an die meldende Person · ${message.author_label ?? ''}`}
            {message.kind === 'NOTE' && `Interne Notiz · ${message.author_label ?? ''}`}
            {message.mark === 'ACKNOWLEDGEMENT' && ' · Eingangsbestätigung'}
            {message.mark === 'FEEDBACK' && ' · Rückmeldung'} · {formatDateTime(message.created_at)}
          </p>
          <p className="whitespace-pre-wrap text-slate-800">{message.body}</p>
        </div>
      ))}
    </section>
  )
}

function Composer({ data }: { data: WhistleCaseDetail }) {
  const send = useWhistleMessageMutation(data.id)
  const [kind, setKind] = useState<'MESSAGE' | 'NOTE'>('MESSAGE')
  const [body, setBody] = useState('')

  function submit(mark: 'ACKNOWLEDGEMENT' | 'FEEDBACK' | null) {
    if (!body.trim()) return
    send.mutate({ kind, body, mark: kind === 'NOTE' ? null : mark }, { onSuccess: () => setBody('') })
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submit(null)
  }

  return (
    <form className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleSubmit} aria-label="Neuer Eintrag">
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="radio" name="whistle-kind" checked={kind === 'MESSAGE'} onChange={() => setKind('MESSAGE')} />
          Nachricht an die meldende Person
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="whistle-kind" checked={kind === 'NOTE'} onChange={() => setKind('NOTE')} />
          Interne Notiz
        </label>
      </div>
      <textarea
        aria-label="Text"
        rows={5}
        maxLength={5000}
        className={TEXTAREA_CLASS}
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      {kind === 'MESSAGE' && (
        <p className="text-xs text-slate-500">Die meldende Person liest die Nachricht mit Vorgangsnummer und Zugangscode; eine E-Mail geht nicht hinaus.</p>
      )}
      {send.error && <p className="text-sm text-red-600">{errorText(send.error)}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={send.isPending || !body.trim()}>
          {kind === 'NOTE' ? 'Notiz speichern' : 'Nachricht senden'}
        </Button>
        {kind === 'MESSAGE' && data.acknowledged_at === null && (
          <Button type="button" variant="outline" disabled={send.isPending || !body.trim()} onClick={() => submit('ACKNOWLEDGEMENT')}>
            Als Eingangsbestätigung senden
          </Button>
        )}
        {kind === 'MESSAGE' && (
          <Button type="button" variant="outline" disabled={send.isPending || !body.trim()} onClick={() => submit('FEEDBACK')}>
            Als Rückmeldung senden
          </Button>
        )}
      </div>
    </form>
  )
}

function Deadlines({ data }: { data: WhistleCaseDetail }) {
  const closed = data.status === 'CLOSED'
  return (
    <section className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4 text-sm" aria-label="Fristen">
      <p className="font-medium text-slate-800">Fristen</p>
      <p>
        Eingangsbestätigung bis{' '}
        <Deadline date={data.ack_due} overdue={data.ack_overdue} done={data.acknowledged_at !== null || closed} />
        {data.acknowledged_at && <span className="block text-xs text-slate-500">bestätigt am {formatDateTime(data.acknowledged_at)}</span>}
      </p>
      <p>
        Rückmeldung bis <Deadline date={data.feedback_due} overdue={data.feedback_overdue} done={data.feedback_at !== null || closed} />
        {data.feedback_at && <span className="block text-xs text-slate-500">erteilt am {formatDateTime(data.feedback_at)}</span>}
      </p>
      {data.delete_after && (
        <p>
          Löschdatum{' '}
          <span className={cn(data.deletion_due && 'font-semibold text-amber-700')}>{formatDate(data.delete_after)}</span>
          <span className="block text-xs text-slate-500">drei Jahre nach Abschluss</span>
        </p>
      )}
    </section>
  )
}

function StatusForm({ data }: { data: WhistleCaseDetail }) {
  const update = useWhistleCaseUpdateMutation(data.id)
  const remove = useDeleteWhistleCaseMutation()
  const navigate = useNavigate()
  const [status, setStatus] = useState<WhistleStatus>(data.status)
  const [note, setNote] = useState(data.closing_note ?? '')
  const [confirmDelete, setConfirmDelete] = useState(false)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    update.mutate({ status, closing_note: status === 'CLOSED' ? note : null })
  }

  return (
    <section className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4" aria-label="Status und Abschluss">
      <form className="flex flex-col gap-2" onSubmit={handleSubmit}>
        <Label htmlFor="whistle-status">Status</Label>
        <select
          id="whistle-status"
          className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value as WhistleStatus)}
        >
          {Object.entries(WHISTLE_STATUS_LABELS).map(([key, text]) => (
            <option key={key} value={key}>
              {text}
            </option>
          ))}
        </select>
        {status === 'CLOSED' && (
          <>
            <Label htmlFor="whistle-closing-note">Abschlussvermerk</Label>
            <textarea
              id="whistle-closing-note"
              rows={4}
              maxLength={4000}
              className={TEXTAREA_CLASS}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <span className="text-xs text-slate-500">Nur für die Meldestelle sichtbar.</span>
          </>
        )}
        {update.error && <p className="text-sm text-red-600">{errorText(update.error)}</p>}
        <Button type="submit" disabled={update.isPending || (status === 'CLOSED' && !note.trim())} className="self-start">
          Speichern
        </Button>
      </form>
      {data.deletion_due && (
        <div className="flex flex-col gap-2 border-t border-slate-100 pt-3">
          <p className="text-sm text-amber-800">Das Löschdatum ist erreicht. Der Vorgang lässt sich jetzt endgültig löschen.</p>
          {confirmDelete ? (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="destructive"
                disabled={remove.isPending}
                onClick={() => remove.mutate(data.id, { onSuccess: () => navigate('/hinweise') })}
              >
                Endgültig löschen
              </Button>
              <Button type="button" variant="outline" onClick={() => setConfirmDelete(false)}>
                Abbrechen
              </Button>
            </div>
          ) : (
            <Button type="button" variant="outline" className="self-start" onClick={() => setConfirmDelete(true)}>
              Vorgang löschen
            </Button>
          )}
          {remove.error && <p className="text-sm text-red-600">{errorText(remove.error)}</p>}
        </div>
      )}
    </section>
  )
}

function Protocol({ data }: { data: WhistleCaseDetail }) {
  return (
    <section className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4 text-sm" aria-label="Protokoll">
      <p className="font-medium text-slate-800">Protokoll</p>
      <ul className="flex flex-col gap-1">
        {data.protocol.map((entry, index) => (
          <li key={`${entry.created_at}-${index}`} className="text-slate-600">
            <span className="text-xs text-slate-500">{formatDateTime(entry.created_at)}</span> · {entry.actor_label}:{' '}
            {entry.detail ?? AUDIT_ACTION_LABELS[entry.action]}
          </li>
        ))}
      </ul>
    </section>
  )
}
