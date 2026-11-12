import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useApplyMutation, useCareerJobQuery, type PublicJobDetail } from '../api/queries/recruiting'
import { PlainText } from '../components/recruiting/PlainText'
import { EMPLOYMENT_TYPE_LABELS, TEXTAREA_CLASS, jobIdFromParam } from '../components/recruiting/labels'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { formatDate } from '../lib/format'
import { CareersShell } from './CareersPage'

const ACCEPT = 'application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg'

function applyError(err: unknown): string {
  if (err instanceof ApiError && err.status === 429) return 'Zu viele Bewerbungen von diesem Anschluss. Bitte später erneut versuchen.'
  if (err instanceof ApiError && err.status === 422) return 'Bitte die Eingaben prüfen (Pflichtfelder, E-Mail-Adresse, Datenschutzhinweise).'
  return err instanceof ApiError ? err.message : 'Die Bewerbung konnte nicht gesendet werden.'
}

function ApplicationForm({ job }: { job: PublicJobDetail }) {
  const apply = useApplyMutation(job.id)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [coverLetter, setCoverLetter] = useState('')
  const [salary, setSalary] = useState('')
  const [privacy, setPrivacy] = useState(false)
  const [talentPool, setTalentPool] = useState(false)
  const [website, setWebsite] = useState('')
  const [cv, setCv] = useState<File | null>(null)
  const [attachments, setAttachments] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const maxBytes = job.max_file_mb * 1024 * 1024

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    const files = [...(cv ? [cv] : []), ...attachments]
    if (files.length > job.max_files) {
      setError(`Höchstens ${job.max_files} Dateien.`)
      return
    }
    if (files.some((file) => file.size > maxBytes)) {
      setError(`Jede Datei darf höchstens ${job.max_file_mb} MB groß sein.`)
      return
    }
    try {
      await apply.mutateAsync({
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        email: email.trim(),
        phone: phone.trim(),
        coverLetter,
        salaryExpectation: salary.trim(),
        privacyAcknowledged: privacy,
        talentPool,
        website,
        cv,
        attachments,
      })
      setSent(true)
    } catch (err) {
      setError(applyError(err))
    }
  }

  if (sent) {
    return (
      <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" role="status">
        Vielen Dank für Ihre Bewerbung! Wir haben Ihre Unterlagen erhalten und melden uns bei Ihnen.
      </div>
    )
  }

  return (
    <form className="flex flex-col gap-4 rounded-md border border-slate-200 bg-white p-4" onSubmit={submit}>
      <h2 className="text-base font-semibold text-slate-900">Jetzt bewerben</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="apply-first">Vorname</Label>
          <Input id="apply-first" required maxLength={100} autoComplete="given-name" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="apply-last">Nachname</Label>
          <Input id="apply-last" required maxLength={100} autoComplete="family-name" value={lastName} onChange={(e) => setLastName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="apply-email">E-Mail</Label>
          <Input id="apply-email" type="email" required maxLength={255} autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="apply-phone">Telefon (optional)</Label>
          <Input id="apply-phone" type="tel" maxLength={40} autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="apply-letter">Anschreiben (optional)</Label>
        <textarea id="apply-letter" rows={6} maxLength={20000} className={TEXTAREA_CLASS} value={coverLetter} onChange={(e) => setCoverLetter(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="apply-salary">Gehaltsvorstellung (optional)</Label>
        <Input id="apply-salary" maxLength={200} value={salary} onChange={(e) => setSalary(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="apply-cv">Lebenslauf (PDF, PNG oder JPEG)</Label>
        <input id="apply-cv" type="file" accept={ACCEPT} className="max-w-full text-sm" onChange={(e) => setCv(e.target.files?.[0] ?? null)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="apply-files">Weitere Anhänge (z. B. Zeugnisse)</Label>
        <input
          id="apply-files"
          type="file"
          multiple
          accept={ACCEPT}
          className="max-w-full text-sm"
          onChange={(e) => setAttachments(Array.from(e.target.files ?? []))}
        />
        <p className="text-xs text-slate-500">
          Insgesamt höchstens {job.max_files} Dateien, je höchstens {job.max_file_mb} MB.
        </p>
      </div>
      {/* Honeypot gegen Bots: für Menschen unsichtbar und nicht erreichbar */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
        <label htmlFor="apply-website">Website</label>
        <input id="apply-website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
      </div>
      {(job.privacy_text || job.privacy_url) && (
        <div className="rounded-md bg-slate-50 p-3 text-xs text-slate-600">
          {job.privacy_text && <PlainText text={job.privacy_text} className="flex flex-col gap-2" />}
          {job.privacy_url && (
            <a href={job.privacy_url} target="_blank" rel="noreferrer" className="underline">
              Datenschutzhinweise für Bewerber
            </a>
          )}
        </div>
      )}
      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input type="checkbox" required className="mt-1" checked={privacy} onChange={(e) => setPrivacy(e.target.checked)} />
        Ich habe die Datenschutzhinweise zur Kenntnis genommen.
      </label>
      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input type="checkbox" className="mt-1" checked={talentPool} onChange={(e) => setTalentPool(e.target.checked)} />
        Meine Bewerbung darf auch für künftige Stellen aufbewahrt werden.
      </label>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <div>
        <Button type="submit" disabled={apply.isPending}>
          Bewerbung absenden
        </Button>
      </div>
    </form>
  )
}

export function CareerJobPage() {
  const { stelle } = useParams()
  const jobId = jobIdFromParam(stelle)
  const job = useCareerJobQuery(jobId)

  if (jobId === null || job.isError) {
    return (
      <CareersShell>
        <p className="text-sm text-slate-600">Diese Stelle gibt es nicht (mehr).</p>
        <Link to="/karriere" className="text-sm underline">
          Alle offenen Stellen
        </Link>
      </CareersShell>
    )
  }
  if (!job.data) {
    return (
      <CareersShell>
        <p className="text-sm text-slate-500">Lädt…</p>
      </CareersShell>
    )
  }
  const data = job.data
  return (
    <CareersShell company={data.company_name}>
      <Link to="/karriere" className="text-sm text-slate-500 underline">
        Alle offenen Stellen
      </Link>
      <article className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
        <h1 className="text-xl font-semibold text-slate-900">{data.title}</h1>
        <p className="text-sm text-slate-600">
          {[EMPLOYMENT_TYPE_LABELS[data.employment_type], data.department, data.location].filter(Boolean).join(' · ')}
        </p>
        {data.application_deadline && (
          <p className="text-xs text-slate-500">Bewerbungsschluss: {formatDate(data.application_deadline)}</p>
        )}
        <PlainText text={data.description} />
      </article>
      <ApplicationForm job={data} />
    </CareersShell>
  )
}
