import { useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { useDepartmentsQuery } from '../../api/queries/departments'
import { useLocationsQuery } from '../../api/queries/locations'
import {
  useSaveJobMutation,
  useTeamCandidatesQuery,
  type EmploymentType,
  type Job,
  type JobStatus,
  type JobWrite,
} from '../../api/queries/recruiting'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { EMPLOYMENT_TYPE_LABELS, JOB_STATUS_LABELS, SELECT_CLASS, TEXTAREA_CLASS } from './labels'

function initial(job: Job | null): JobWrite {
  return {
    title: job?.title ?? '',
    department_id: job?.department_id ?? null,
    location_id: job?.location_id ?? null,
    employment_type: job?.employment_type ?? 'FULL_TIME',
    description: job?.description ?? '',
    status: job?.status ?? 'DRAFT',
    application_deadline: job?.application_deadline ?? null,
    member_account_ids: job?.members.map((member) => member.account_id) ?? [],
  }
}

/** Stelle anlegen oder bearbeiten (Admin/HR). */
export function JobDialog({ job, open, onClose }: { job: Job | null; open: boolean; onClose: () => void }) {
  const [form, setForm] = useState<JobWrite>(() => initial(job))
  const [error, setError] = useState<string | null>(null)
  const departments = useDepartmentsQuery(open)
  const locations = useLocationsQuery(open)
  const candidates = useTeamCandidatesQuery(open)
  const save = useSaveJobMutation()

  const set = <K extends keyof JobWrite>(key: K, value: JobWrite[K]) => setForm((current) => ({ ...current, [key]: value }))
  const members = form.member_account_ids ?? []

  function toggleMember(accountId: number, checked: boolean) {
    set('member_account_ids', checked ? [...members, accountId] : members.filter((id) => id !== accountId))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await save.mutateAsync({ id: job?.id, payload: { ...form, title: form.title.trim() } })
      onClose()
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Speichern fehlgeschlagen – bitte Eingaben prüfen.')
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{job ? 'Stelle bearbeiten' : 'Neue Stelle'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div className="flex flex-col gap-1">
            <Label htmlFor="job-title">Titel</Label>
            <Input id="job-title" required maxLength={200} value={form.title} onChange={(e) => set('title', e.target.value)} />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="job-department">Abteilung</Label>
              <select
                id="job-department"
                className={SELECT_CLASS}
                value={form.department_id ?? ''}
                onChange={(e) => set('department_id', e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Keine Angabe</option>
                {(departments.data ?? []).map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="job-location">Standort</Label>
              <select
                id="job-location"
                className={SELECT_CLASS}
                value={form.location_id ?? ''}
                onChange={(e) => set('location_id', e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Keine Angabe</option>
                {(locations.data ?? []).map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="job-type">Anstellungsart</Label>
              <select
                id="job-type"
                className={SELECT_CLASS}
                value={form.employment_type}
                onChange={(e) => set('employment_type', e.target.value as EmploymentType)}
              >
                {Object.entries(EMPLOYMENT_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="job-status">Status</Label>
              <select
                id="job-status"
                className={SELECT_CLASS}
                value={form.status}
                onChange={(e) => set('status', e.target.value as JobStatus)}
              >
                {Object.entries(JOB_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="job-deadline">Bewerbungsschluss (optional)</Label>
              <Input
                id="job-deadline"
                type="date"
                value={form.application_deadline ?? ''}
                onChange={(e) => set('application_deadline', e.target.value || null)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="job-description">Beschreibung</Label>
            <textarea
              id="job-description"
              rows={8}
              maxLength={20000}
              className={TEXTAREA_CLASS}
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
            />
            <p className="text-xs text-slate-500">
              Einfacher Text: Leerzeile = neuer Absatz, Zeilen mit „- “ am Anfang werden zur Aufzählung.
            </p>
          </div>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium text-slate-800">Hiring Team</legend>
            <p className="text-xs text-slate-500">
              Diese Konten sehen und bewerten die Bewerbungen dieser Stelle – zusätzlich zu Admin und HR.
            </p>
            <div className="grid max-h-48 grid-cols-1 gap-1 overflow-y-auto sm:grid-cols-2">
              {(candidates.data ?? []).map((candidate) => (
                <label key={candidate.account_id} className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={members.includes(candidate.account_id)}
                    onChange={(e) => toggleMember(candidate.account_id, e.target.checked)}
                  />
                  <span className="truncate">
                    {candidate.name}
                    {candidate.email && candidate.email !== candidate.name && (
                      <span className="text-slate-400"> · {candidate.email}</span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={save.isPending}>
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
