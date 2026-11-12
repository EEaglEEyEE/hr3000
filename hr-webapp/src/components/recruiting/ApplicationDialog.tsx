import { useState, type FormEvent } from 'react'
import { Download, Eye, Star, Trash2, Upload } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  openAttachment,
  useApplicationActions,
  useApplicationQuery,
  type ApplicationDetail,
  type AttachmentKind,
  type RejectionReason,
  type Stage,
} from '../../api/queries/recruiting'
import { formatDate, formatDateTime } from '../../lib/format'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { HireDialog } from './HireDialog'
import { PlainText } from './PlainText'
import {
  REJECTION_REASON_LABELS,
  SELECT_CLASS,
  SOURCE_LABELS,
  STAGES,
  STAGE_LABELS,
  STAGE_VARIANT,
  TEXTAREA_CLASS,
} from './labels'

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.status !== 422 ? err.message : fallback
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t border-slate-200 pt-3">
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      {children}
    </section>
  )
}

function StageForm({ application, onError }: { application: ApplicationDetail; onError: (text: string | null) => void }) {
  const { stage } = useApplicationActions(application.id)
  const [next, setNext] = useState<Stage>(application.stage)
  const [reason, setReason] = useState<RejectionReason | ''>(application.rejection_reason ?? '')
  const [note, setNote] = useState(application.rejection_note ?? '')
  const closing = next === 'REJECTED' || next === 'WITHDRAWN'
  const locked = application.employee_id != null

  async function submit(event: FormEvent) {
    event.preventDefault()
    onError(null)
    try {
      await stage.mutateAsync({
        stage: next,
        rejection_reason: next === 'REJECTED' ? (reason || null) : null,
        rejection_note: closing ? note.trim() || null : null,
      })
    } catch (err) {
      onError(errorText(err, 'Phasenwechsel fehlgeschlagen – bei „Abgelehnt“ bitte einen Grund wählen.'))
    }
  }

  return (
    <form className="flex flex-col gap-2" onSubmit={submit}>
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="stage-select">Phase</Label>
          <select
            id="stage-select"
            className={`${SELECT_CLASS} w-44`}
            value={next}
            disabled={locked}
            onChange={(e) => setNext(e.target.value as Stage)}
          >
            {STAGES.map((value) => (
              <option key={value} value={value}>
                {STAGE_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
        {next === 'REJECTED' && (
          <div className="flex flex-col gap-1">
            <Label htmlFor="stage-reason">Absagegrund</Label>
            <select
              id="stage-reason"
              required
              className={`${SELECT_CLASS} w-56`}
              value={reason}
              onChange={(e) => setReason(e.target.value as RejectionReason)}
            >
              <option value="">Bitte wählen</option>
              {Object.entries(REJECTION_REASON_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        )}
        <Button type="submit" size="sm" disabled={stage.isPending || locked}>
          Phase speichern
        </Button>
      </div>
      {closing && (
        <Input
          aria-label="Begründung (optional)"
          placeholder="Begründung (optional)"
          maxLength={500}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      )}
      {locked && <p className="text-xs text-slate-500">Bereits als Mitarbeiter übernommen.</p>}
    </form>
  )
}

function RatingForm({ application, onError }: { application: ApplicationDetail; onError: (text: string | null) => void }) {
  const { rate, unrate } = useApplicationActions(application.id)
  const mine = application.ratings.find((rating) => rating.mine)
  const [score, setScore] = useState(mine?.score ?? 0)
  const [comment, setComment] = useState(mine?.comment ?? '')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (score < 1) return
    onError(null)
    try {
      await rate.mutateAsync({ score, comment: comment.trim() || null })
    } catch (err) {
      onError(errorText(err, 'Bewertung fehlgeschlagen.'))
    }
  }

  return (
    <form className="flex flex-col gap-2" onSubmit={submit}>
      <div className="flex items-center gap-1" role="radiogroup" aria-label="Meine Bewertung">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={score === value}
            aria-label={`${value} von 5`}
            onClick={() => setScore(value)}
            className="rounded p-0.5 text-amber-500"
          >
            <Star className="h-5 w-5" fill={value <= score ? 'currentColor' : 'none'} />
          </button>
        ))}
      </div>
      <Input aria-label="Kommentar zur Bewertung" placeholder="Kommentar (optional)" maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={score < 1 || rate.isPending}>
          Bewertung speichern
        </Button>
        {mine && (
          <Button type="button" size="sm" variant="outline" onClick={() => void unrate.mutateAsync().then(() => setScore(0))}>
            Bewertung entfernen
          </Button>
        )}
      </div>
    </form>
  )
}

function Details({ application, departmentId, locationId, onClose }: {
  application: ApplicationDetail
  departmentId?: number | null
  locationId?: number | null
  onClose: () => void
}) {
  const actions = useApplicationActions(application.id)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState<AttachmentKind>('CV')
  const [hiring, setHiring] = useState(false)
  const manage = application.can_manage

  async function run(action: () => Promise<unknown>, fallback: string) {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(errorText(err, fallback))
    }
  }

  async function addNote(event: FormEvent) {
    event.preventDefault()
    if (!note.trim()) return
    await run(async () => {
      await actions.addNote.mutateAsync(note.trim())
      setNote('')
    }, 'Notiz konnte nicht gespeichert werden.')
  }

  async function upload(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    await run(async () => {
      await actions.upload.mutateAsync({ file, kind })
      setFile(null)
    }, 'Hochladen fehlgeschlagen.')
  }

  async function remove() {
    if (!window.confirm('Bewerbung mit allen Notizen, Bewertungen und Anhängen endgültig löschen? Das lässt sich nicht rückgängig machen.')) return
    await run(async () => {
      await actions.remove.mutateAsync()
      onClose()
    }, 'Löschen fehlgeschlagen.')
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <Badge variant={STAGE_VARIANT[application.stage]}>{STAGE_LABELS[application.stage]}</Badge>
        <span>{application.job_title}</span>
        <span>· {SOURCE_LABELS[application.source]}</span>
        <span>· eingegangen am {formatDate(application.created_at)}</span>
        {application.talent_pool && <Badge variant="info">Talentpool</Badge>}
      </div>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-slate-500">E-Mail</dt>
        <dd>
          <a className="underline" href={`mailto:${application.email}`}>
            {application.email}
          </a>
        </dd>
        <dt className="text-slate-500">Telefon</dt>
        <dd>{application.phone || '–'}</dd>
        {application.salary_visible && (
          <>
            <dt className="text-slate-500">Gehaltsvorstellung</dt>
            <dd>{application.salary_expectation || '–'}</dd>
          </>
        )}
        {application.rejection_reason && (
          <>
            <dt className="text-slate-500">Absagegrund</dt>
            <dd>{REJECTION_REASON_LABELS[application.rejection_reason]}</dd>
          </>
        )}
        {application.rejection_note && (
          <>
            <dt className="text-slate-500">Begründung</dt>
            <dd>{application.rejection_note}</dd>
          </>
        )}
        {application.delete_on && (
          <>
            <dt className="text-slate-500">Wird gelöscht am</dt>
            <dd>{formatDate(application.delete_on)}</dd>
          </>
        )}
      </dl>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Section title="Phase">
        <StageForm key={`${application.stage}-${application.rejection_reason}`} application={application} onError={setError} />
        {manage && application.stage === 'HIRED' && application.employee_id == null && (
          <div>
            <Button size="sm" onClick={() => setHiring(true)}>
              Als Mitarbeiter übernehmen
            </Button>
          </div>
        )}
      </Section>

      {application.cover_letter && (
        <Section title="Anschreiben">
          <PlainText text={application.cover_letter} />
        </Section>
      )}

      <Section title="Anhänge">
        {application.attachments.length === 0 && <p className="text-sm text-slate-500">Keine Anhänge.</p>}
        <ul className="flex flex-col gap-1">
          {application.attachments.map((attachment) => (
            <li key={attachment.id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{attachment.kind === 'CV' ? 'Lebenslauf' : 'Anhang'}:</span>
              <span className="truncate">{attachment.original_filename}</span>
              <span className="text-xs text-slate-400">{Math.ceil(attachment.size_bytes / 1024)} KB</span>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`${attachment.original_filename} ansehen`}
                onClick={() => void run(() => openAttachment(application.id, attachment.id, attachment.original_filename, true), 'Ansehen fehlgeschlagen.')}
              >
                <Eye className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`${attachment.original_filename} herunterladen`}
                onClick={() => void run(() => openAttachment(application.id, attachment.id, attachment.original_filename, false), 'Download fehlgeschlagen.')}
              >
                <Download className="h-4 w-4" />
              </Button>
              {manage && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`${attachment.original_filename} löschen`}
                  onClick={() =>
                    window.confirm(`Anhang „${attachment.original_filename}“ löschen?`) &&
                    void run(() => actions.deleteAttachment.mutateAsync(attachment.id), 'Löschen fehlgeschlagen.')
                  }
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
        {manage && (
          <form className="flex flex-wrap items-center gap-2" onSubmit={upload}>
            <input
              type="file"
              aria-label="Anhang wählen"
              accept="application/pdf,image/png,image/jpeg"
              className="max-w-full text-sm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <select aria-label="Art des Anhangs" className={`${SELECT_CLASS} w-36`} value={kind} onChange={(e) => setKind(e.target.value as AttachmentKind)}>
              <option value="CV">Lebenslauf</option>
              <option value="OTHER">Sonstiges</option>
            </select>
            <Button type="submit" size="sm" variant="outline" disabled={!file || actions.upload.isPending}>
              <Upload className="h-4 w-4" /> Hochladen
            </Button>
          </form>
        )}
      </Section>

      <Section title="Bewertungen">
        {application.ratings.length > 0 && (
          <ul className="flex flex-col gap-1 text-sm">
            {application.ratings.map((rating) => (
              <li key={rating.account_id}>
                <span className="font-medium">{rating.name ?? 'Unbekannt'}</span>: {'★'.repeat(rating.score)}
                {'☆'.repeat(5 - rating.score)}
                {rating.comment && <span className="text-slate-500"> – {rating.comment}</span>}
              </li>
            ))}
          </ul>
        )}
        <RatingForm key={application.ratings.find((r) => r.mine)?.updated_at ?? 'none'} application={application} onError={setError} />
      </Section>

      <Section title="Notizen">
        <ul className="flex flex-col gap-2">
          {application.notes.map((item) => (
            <li key={item.id} className="rounded-md bg-slate-50 p-2 text-sm">
              <div className="flex items-center justify-between gap-2 text-xs text-slate-500">
                <span>
                  {item.author_name ?? 'Unbekannt'} · {formatDateTime(item.created_at)}
                </span>
                {item.can_delete && (
                  <button
                    type="button"
                    className="underline"
                    onClick={() => void run(() => actions.deleteNote.mutateAsync(item.id), 'Löschen fehlgeschlagen.')}
                  >
                    Löschen
                  </button>
                )}
              </div>
              <PlainText text={item.body} className="mt-1 flex flex-col gap-2 text-sm text-slate-700" />
            </li>
          ))}
        </ul>
        <form className="flex flex-col gap-2" onSubmit={addNote}>
          <textarea aria-label="Neue Notiz" rows={2} maxLength={5000} className={TEXTAREA_CLASS} value={note} onChange={(e) => setNote(e.target.value)} />
          <div>
            <Button type="submit" size="sm" variant="outline" disabled={!note.trim() || actions.addNote.isPending}>
              Notiz hinzufügen
            </Button>
          </div>
        </form>
      </Section>

      <Section title="Verlauf">
        <ul className="flex flex-col gap-1 text-sm text-slate-600">
          {application.events.map((event, index) => (
            <li key={index}>
              {formatDateTime(event.created_at)}:{' '}
              {event.from_stage ? `${STAGE_LABELS[event.from_stage]} → ${STAGE_LABELS[event.to_stage]}` : 'Eingang'}
              {event.account_name && ` (${event.account_name})`}
            </li>
          ))}
        </ul>
      </Section>

      {manage && (
        <Section title="Verwaltung">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={application.talent_pool}
              onChange={(e) => void run(() => actions.update.mutateAsync({ talent_pool: e.target.checked }), 'Speichern fehlgeschlagen.')}
            />
            Für künftige Stellen aufbewahren (Talentpool, verlängerte Löschfrist)
          </label>
          <div>
            <Button size="sm" variant="destructive" onClick={() => void remove()}>
              Bewerbung jetzt löschen
            </Button>
          </div>
        </Section>
      )}
      {hiring && (
        <HireDialog application={application} departmentId={departmentId} locationId={locationId} onClose={() => setHiring(false)} />
      )}
    </div>
  )
}

/** Detailansicht einer Bewerbung als Dialog. */
export function ApplicationDialog({
  applicationId,
  departmentId,
  locationId,
  onClose,
}: {
  applicationId: number
  departmentId?: number | null
  locationId?: number | null
  onClose: () => void
}) {
  const query = useApplicationQuery(applicationId)
  const application = query.data
  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{application ? `${application.first_name} ${application.last_name}` : 'Bewerbung'}</DialogTitle>
        </DialogHeader>
        {query.isLoading && <p className="text-sm text-slate-500">Lädt…</p>}
        {query.isError && <p className="text-sm text-red-600">Die Bewerbung konnte nicht geladen werden.</p>}
        {application && (
          <Details
            application={application}
            departmentId={departmentId}
            locationId={locationId}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
