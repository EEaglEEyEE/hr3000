import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  fetchWhistleCase,
  fetchWhistleInfo,
  sendWhistleMessage,
  submitWhistleReport,
  uploadWhistleAttachment,
  type WhistleAccess,
  type WhistleCreated,
  type WhistleInfo,
  type WhistlePublicCase,
  type WhistleReport,
} from '../api/whistlePublic'
import { BrandLogo } from '../components/layout/BrandLogo'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { formatBytes, formatDateTime, TEXTAREA_CLASS } from '../components/whistle/textarea'
import { WHISTLE_CATEGORY_LABELS, WHISTLE_STATUS_LABELS } from '../lib/labels'
import { cn } from '../lib/utils'

const DESCRIPTION_MIN = 10
const DESCRIPTION_MAX = 10000
const MESSAGE_MAX = 5000
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.docx,.xlsx'

function errorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.status !== 422) return error.message
  return fallback
}

/** Öffentliche Meldeseite des Hinweisgebersystems – ohne Anmeldung, siehe api/whistlePublic.ts. */
export function WhistleReportPage() {
  const [info, setInfo] = useState<WhistleInfo | null | undefined>(undefined)
  const [loadError, setLoadError] = useState(false)
  const [mode, setMode] = useState<'report' | 'status'>('report')

  useEffect(() => {
    fetchWhistleInfo()
      .then(setInfo)
      .catch(() => setLoadError(true))
  }, [])

  return (
    <div className="min-h-screen bg-slate-100 p-4">
      <Card className="mx-auto w-full max-w-2xl">
        <CardHeader>
          <BrandLogo size="lg" />
          <CardTitle className="mt-3">Hinweisgebersystem{info ? ` – ${info.company_name}` : ''}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {loadError && <p className="text-sm text-red-600">Die Seite konnte nicht geladen werden. Bitte später erneut versuchen.</p>}
          {info === undefined && !loadError && <p className="text-sm text-slate-500">Lädt…</p>}
          {info === null && (
            <p className="text-sm text-slate-700" role="status">
              Diese Firma hat hier kein Hinweisgebersystem eingerichtet.
            </p>
          )}
          {info && (
            <>
              <div className="flex gap-2" role="tablist" aria-label="Bereich">
                {(
                  [
                    ['report', 'Hinweis abgeben'],
                    ['status', 'Stand abfragen'],
                  ] as const
                ).map(([key, text]) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={mode === key}
                    onClick={() => setMode(key)}
                    className={cn(
                      'rounded-md px-3 py-1.5 text-sm font-medium',
                      mode === key ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100',
                    )}
                  >
                    {text}
                  </button>
                ))}
              </div>
              {mode === 'report' ? <ReportForm info={info} /> : <StatusView info={info} />}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Notice({ info }: { info: WhistleInfo }) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-slate-50 p-3 text-sm text-slate-600">
      <p>
        Ihre Meldung geht ausschließlich an die von {info.company_name} benannte interne Meldestelle. Wer eine Meldung
        abgibt, muss sich nicht anmelden; die Seite speichert weder Ihre IP-Adresse noch eine Verbindung zu einem
        Benutzerkonto.
      </p>
      <p>
        Dateien können Metadaten enthalten (z. B. Autor, Gerät, Aufnahmeort bei Fotos). Wenn Sie anonym bleiben möchten,
        entfernen Sie diese vor dem Hochladen.
      </p>
    </div>
  )
}

function ReportForm({ info }: { info: WhistleInfo }) {
  const [category, setCategory] = useState<WhistleReport['category'] | ''>('')
  const [description, setDescription] = useState('')
  const [occurredWhen, setOccurredWhen] = useState('')
  const [occurredWhere, setOccurredWhere] = useState('')
  const [anonymous, setAnonymous] = useState(true)
  const [contactName, setContactName] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [created, setCreated] = useState<WhistleCreated | null>(null)
  const [uploadErrors, setUploadErrors] = useState<string[]>([])

  if (!info.accepting_reports) {
    return (
      <p className="text-sm text-slate-700" role="status">
        Derzeit können hier keine neuen Hinweise abgegeben werden. Bitte wenden Sie sich an die Personalabteilung oder an
        eine externe Meldestelle.
      </p>
    )
  }

  if (created) return <Created created={created} uploadErrors={uploadErrors} />

  function pickFiles(list: FileList | null) {
    const picked = Array.from(list ?? [])
    const tooBig = picked.find((file) => file.size > info.max_attachment_bytes)
    if (tooBig) return setError(`„${tooBig.name}“ ist größer als ${formatBytes(info.max_attachment_bytes)}.`)
    if (picked.length > info.max_attachments) return setError(`Höchstens ${info.max_attachments} Dateien.`)
    setError(null)
    setFiles(picked)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!category) return setError('Bitte eine Kategorie wählen.')
    if (description.trim().length < DESCRIPTION_MIN) {
      return setError(`Bitte beschreiben Sie den Sachverhalt mit mindestens ${DESCRIPTION_MIN} Zeichen.`)
    }
    if (!anonymous && !contactName.trim() && !contactEmail.trim()) {
      return setError('Bitte Name oder E-Mail-Adresse angeben – oder die Meldung anonym abgeben.')
    }
    setPending(true)
    try {
      const result = await submitWhistleReport({
        category,
        description,
        occurred_when: occurredWhen.trim() || null,
        occurred_where: occurredWhere.trim() || null,
        anonymous,
        contact_name: anonymous ? null : contactName.trim() || null,
        contact_email: anonymous ? null : contactEmail.trim() || null,
      })
      const access = { case_number: result.case_number, access_code: result.access_code }
      const failed: string[] = []
      for (const file of files) {
        try {
          await uploadWhistleAttachment(access, file)
        } catch (err) {
          failed.push(`${file.name}: ${errorText(err, 'konnte nicht hochgeladen werden.')}`)
        }
      }
      setUploadErrors(failed)
      setCreated(result)
    } catch (err) {
      setError(errorText(err, 'Bitte die Eingaben prüfen.'))
    } finally {
      setPending(false)
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
      <Notice info={info} />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="whistle-category">Kategorie</Label>
        <select
          id="whistle-category"
          required
          className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
          value={category}
          onChange={(e) => setCategory(e.target.value as WhistleReport['category'])}
        >
          <option value="">Bitte wählen</option>
          {Object.entries(WHISTLE_CATEGORY_LABELS).map(([key, text]) => (
            <option key={key} value={key}>
              {text}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="whistle-description">Beschreibung</Label>
        <textarea
          id="whistle-description"
          required
          rows={8}
          maxLength={DESCRIPTION_MAX}
          className={TEXTAREA_CLASS}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Was ist passiert? Wer war beteiligt? Woher wissen Sie davon?"
        />
        <span className="text-xs text-slate-500">
          {description.length} / {DESCRIPTION_MAX} Zeichen
        </span>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="whistle-when">Zeitpunkt (freiwillig)</Label>
          <Input id="whistle-when" maxLength={200} value={occurredWhen} onChange={(e) => setOccurredWhen(e.target.value)} placeholder="z. B. Anfang Oktober" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="whistle-where">Ort (freiwillig)</Label>
          <Input id="whistle-where" maxLength={200} value={occurredWhere} onChange={(e) => setOccurredWhere(e.target.value)} />
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="whistle-files">Anhänge (freiwillig)</Label>
        <input
          id="whistle-files"
          type="file"
          multiple
          accept={ACCEPT}
          className="text-sm"
          onChange={(e) => pickFiles(e.target.files)}
        />
        <span className="text-xs text-slate-500">
          PDF, PNG, JPEG, DOCX oder XLSX, je Datei höchstens {formatBytes(info.max_attachment_bytes)}.
        </span>
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium text-slate-800">Kontakt</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="whistle-contact" checked={anonymous} onChange={() => setAnonymous(true)} />
          Anonym melden
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="whistle-contact" checked={!anonymous} onChange={() => setAnonymous(false)} />
          Mit Kontaktangabe melden
        </label>
        {!anonymous && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="whistle-name">Name</Label>
              <Input id="whistle-name" maxLength={200} value={contactName} onChange={(e) => setContactName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="whistle-email">E-Mail</Label>
              <Input id="whistle-email" type="email" maxLength={255} value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} />
            </div>
          </div>
        )}
        <span className="text-xs text-slate-500">
          Auch bei einer anonymen Meldung können Sie später mit Vorgangsnummer und Zugangscode Rückfragen beantworten.
        </span>
      </fieldset>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending}>
        {pending ? 'Sende…' : 'Hinweis absenden'}
      </Button>
    </form>
  )
}

function Created({ created, uploadErrors }: { created: WhistleCreated; uploadErrors: string[] }) {
  return (
    <div className="flex flex-col gap-3" role="status">
      <p className="text-sm text-slate-700">Ihr Hinweis ist eingegangen. Bitte notieren Sie sich jetzt diese beiden Angaben:</p>
      <dl className="grid grid-cols-1 gap-2 rounded-md border border-amber-300 bg-amber-50 p-4 sm:grid-cols-[auto_1fr]">
        <dt className="text-sm text-slate-600">Vorgangsnummer</dt>
        <dd className="font-mono text-lg font-semibold text-slate-900">{created.case_number}</dd>
        <dt className="text-sm text-slate-600">Zugangscode</dt>
        <dd className="break-all font-mono text-lg font-semibold text-slate-900">{created.access_code}</dd>
      </dl>
      <p className="text-sm text-slate-700">
        Der Zugangscode wird nur dieses eine Mal angezeigt und lässt sich nicht wiederherstellen. Mit beiden Angaben sehen
        Sie unter „Stand abfragen“ den Bearbeitungsstand, lesen Nachrichten der Meldestelle, antworten darauf und reichen
        Dateien nach.
      </p>
      {uploadErrors.length > 0 && (
        <div className="text-sm text-red-600" role="alert">
          <p>Einige Dateien wurden nicht übernommen – Sie können sie unter „Stand abfragen“ erneut hochladen:</p>
          <ul className="list-disc pl-5">
            {uploadErrors.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function StatusView({ info }: { info: WhistleInfo }) {
  const [caseNumber, setCaseNumber] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [access, setAccess] = useState<WhistleAccess | null>(null)
  const [data, setData] = useState<WhistlePublicCase | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setPending(true)
    const candidate = { case_number: caseNumber.trim(), access_code: accessCode.trim() }
    try {
      setData(await fetchWhistleCase(candidate))
      setAccess(candidate)
      // Den Code nicht länger als nötig im Formular halten
      setAccessCode('')
    } catch (err) {
      setError(errorText(err, 'Vorgangsnummer oder Zugangscode stimmen nicht.'))
    } finally {
      setPending(false)
    }
  }

  if (data && access) {
    return (
      <CaseView
        info={info}
        access={access}
        data={data}
        onChange={setData}
        onLeave={() => {
          setData(null)
          setAccess(null)
        }}
      />
    )
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="whistle-number">Vorgangsnummer</Label>
          <Input id="whistle-number" required autoComplete="off" maxLength={20} value={caseNumber} onChange={(e) => setCaseNumber(e.target.value)} placeholder="H-…" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="whistle-code">Zugangscode</Label>
          <Input id="whistle-code" required type="password" autoComplete="off" maxLength={60} value={accessCode} onChange={(e) => setAccessCode(e.target.value)} />
        </div>
      </div>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending}>
        {pending ? 'Prüfe…' : 'Stand abfragen'}
      </Button>
    </form>
  )
}

function CaseView({
  info,
  access,
  data,
  onChange,
  onLeave,
}: {
  info: WhistleInfo
  access: WhistleAccess
  data: WhistlePublicCase
  onChange: (data: WhistlePublicCase) => void
  onLeave: () => void
}) {
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function run(action: () => Promise<WhistlePublicCase>, fallback: string) {
    setError(null)
    setPending(true)
    try {
      onChange(await action())
      return true
    } catch (err) {
      setError(errorText(err, fallback))
      return false
    } finally {
      setPending(false)
    }
  }

  async function handleMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!message.trim()) return
    if (await run(() => sendWhistleMessage(access, message), 'Die Nachricht konnte nicht gesendet werden.')) setMessage('')
  }

  async function handleFile(file: File | undefined) {
    if (!file) return
    if (file.size > info.max_attachment_bytes) return setError(`Die Datei ist größer als ${formatBytes(info.max_attachment_bytes)}.`)
    await run(() => uploadWhistleAttachment(access, file), 'Die Datei konnte nicht hochgeladen werden.')
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-slate-700">
          Vorgang <span className="font-mono font-semibold">{data.case_number}</span> · {WHISTLE_CATEGORY_LABELS[data.category]}
        </p>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">{WHISTLE_STATUS_LABELS[data.status]}</span>
      </div>
      <p className="text-xs text-slate-500">
        Eingegangen am {formatDateTime(data.received_at)}
        {data.acknowledged_at ? ` · Eingang bestätigt am ${formatDateTime(data.acknowledged_at)}` : ''}
      </p>
      <details className="rounded-md border border-slate-200 p-3 text-sm">
        <summary className="cursor-pointer font-medium text-slate-800">Ihre Meldung</summary>
        <p className="mt-2 whitespace-pre-wrap text-slate-700">{data.description}</p>
      </details>

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium text-slate-800">Nachrichten</p>
        {data.messages.length === 0 && <p className="text-sm text-slate-500">Noch keine Nachrichten.</p>}
        {data.messages.map((entry, index) => (
          <div
            key={`${entry.created_at}-${index}`}
            className={cn('rounded-md p-3 text-sm', entry.from_office ? 'bg-sky-50 text-slate-800' : 'ml-6 bg-slate-50 text-slate-700')}
          >
            <p className="mb-1 text-xs text-slate-500">
              {entry.from_office ? 'Meldestelle' : 'Sie'} · {formatDateTime(entry.created_at)}
            </p>
            <p className="whitespace-pre-wrap">{entry.body}</p>
          </div>
        ))}
      </div>

      {data.status !== 'CLOSED' && (
        <form className="flex flex-col gap-2" onSubmit={handleMessage}>
          <Label htmlFor="whistle-reply">Antwort an die Meldestelle</Label>
          <textarea
            id="whistle-reply"
            rows={4}
            maxLength={MESSAGE_MAX}
            className={TEXTAREA_CLASS}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <Button type="submit" disabled={pending || !message.trim()} className="self-start">
            Nachricht senden
          </Button>
        </form>
      )}

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium text-slate-800">Anhänge</p>
        {data.attachments.length === 0 && <p className="text-sm text-slate-500">Keine Anhänge.</p>}
        <ul className="text-sm text-slate-700">
          {data.attachments.map((file, index) => (
            <li key={`${file.created_at}-${index}`}>
              {file.filename} ({formatBytes(file.size_bytes)})
            </li>
          ))}
        </ul>
        {data.status !== 'CLOSED' && data.attachments.length < info.max_attachments && (
          <label className="flex flex-col gap-1 text-sm">
            <span>Datei nachreichen</span>
            <input type="file" accept={ACCEPT} disabled={pending} aria-label="Datei nachreichen" onChange={(e) => void handleFile(e.target.files?.[0])} />
            <span className="text-xs text-slate-500">Dateien können Metadaten enthalten – vor dem Hochladen ggf. entfernen.</span>
          </label>
        )}
      </div>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <Button type="button" variant="outline" onClick={onLeave} className="self-start">
        Vorgang schließen
      </Button>
    </div>
  )
}
