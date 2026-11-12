import { useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { useCreateApplicationMutation, type ApplicationDetail, type Job } from '../../api/queries/recruiting'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { SELECT_CLASS, TEXTAREA_CLASS } from './labels'

/** Bewerbung manuell erfassen (z. B. per Post oder E-Mail eingegangen) – Admin/HR. */
export function NewApplicationDialog({
  jobs,
  defaultJobId,
  canSeeSalary,
  onClose,
  onCreated,
}: {
  jobs: Job[]
  defaultJobId?: number
  canSeeSalary: boolean
  onClose: () => void
  onCreated: (application: ApplicationDetail) => void
}) {
  const [jobId, setJobId] = useState<number | ''>(defaultJobId ?? jobs[0]?.id ?? '')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [coverLetter, setCoverLetter] = useState('')
  const [salary, setSalary] = useState('')
  const [talentPool, setTalentPool] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const create = useCreateApplicationMutation()

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (jobId === '') return
    setError(null)
    try {
      const created = await create.mutateAsync({
        job_id: jobId,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        phone: phone.trim() || null,
        cover_letter: coverLetter || null,
        salary_expectation: canSeeSalary ? salary.trim() || null : null,
        talent_pool: talentPool,
      })
      onCreated(created)
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Speichern fehlgeschlagen – bitte Eingaben prüfen.')
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Bewerbung erfassen</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1">
            <Label htmlFor="new-app-job">Stelle</Label>
            <select
              id="new-app-job"
              required
              className={SELECT_CLASS}
              value={jobId}
              onChange={(e) => setJobId(e.target.value ? Number(e.target.value) : '')}
            >
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-app-first">Vorname</Label>
              <Input id="new-app-first" required maxLength={100} value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-app-last">Nachname</Label>
              <Input id="new-app-last" required maxLength={100} value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-app-email">E-Mail</Label>
              <Input id="new-app-email" type="email" required maxLength={255} value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-app-phone">Telefon (optional)</Label>
              <Input id="new-app-phone" maxLength={40} value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="new-app-letter">Anschreiben (optional)</Label>
            <textarea id="new-app-letter" rows={4} maxLength={20000} className={TEXTAREA_CLASS} value={coverLetter} onChange={(e) => setCoverLetter(e.target.value)} />
          </div>
          {canSeeSalary && (
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-app-salary">Gehaltsvorstellung (optional)</Label>
              <Input id="new-app-salary" maxLength={200} value={salary} onChange={(e) => setSalary(e.target.value)} />
            </div>
          )}
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={talentPool} onChange={(e) => setTalentPool(e.target.checked)} />
            Bewerbung für künftige Stellen aufbewahren (Talentpool)
          </label>
          <p className="text-xs text-slate-500">Anhänge lädst du danach in der Bewerbung hoch.</p>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={create.isPending || jobId === ''}>
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
