import { useState } from 'react'
import { ExternalLink, Pencil, Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import { useDeleteJobMutation, useJobsQuery, type Job } from '../../api/queries/recruiting'
import { formatDate } from '../../lib/format'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { JobDialog } from './JobDialog'
import { EMPLOYMENT_TYPE_LABELS, JOB_STATUS_LABELS, JOB_STATUS_VARIANT, STAGE_LABELS, careerPath } from './labels'

function deletedSummary(job: Job): string | null {
  const entries = Object.entries(job.deleted_counts ?? {})
  if (entries.length === 0) return null
  return entries.map(([stage, count]) => `${count} × ${STAGE_LABELS[stage as keyof typeof STAGE_LABELS] ?? stage}`).join(', ')
}

/** Reiter „Stellen“: Liste; Admin/HR legen an, bearbeiten und löschen. */
export function JobsTab({ canManage, onShowApplications }: { canManage: boolean; onShowApplications: (jobId: number) => void }) {
  const jobs = useJobsQuery()
  const remove = useDeleteJobMutation()
  const [editing, setEditing] = useState<Job | null>(null)
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function deleteJob(job: Job) {
    if (!window.confirm(`Stelle „${job.title}“ löschen?`)) return
    setMessage(null)
    try {
      await remove.mutateAsync(job.id)
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Löschen fehlgeschlagen.')
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500">
          Veröffentlichte Stellen stehen bis zum Bewerbungsschluss auf der{' '}
          <a href="/karriere" target="_blank" rel="noreferrer" className="underline">
            Karriereseite
          </a>
          .
        </p>
        {canManage && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" /> Neue Stelle
          </Button>
        )}
      </div>
      {message && <p className="text-sm text-red-600">{message}</p>}
      {jobs.isLoading && <p className="text-sm text-slate-500">Lädt…</p>}
      {jobs.data && jobs.data.length === 0 && <p className="text-sm text-slate-500">Noch keine Stellen.</p>}
      {jobs.data && jobs.data.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stelle</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Abteilung / Standort</TableHead>
                <TableHead>Bewerbungsschluss</TableHead>
                <TableHead>Bewerbungen</TableHead>
                <TableHead>Hiring Team</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.data.map((job) => (
                <TableRow key={job.id}>
                  <TableCell>
                    <div className="font-medium text-slate-900">{job.title}</div>
                    <div className="text-xs text-slate-500">{EMPLOYMENT_TYPE_LABELS[job.employment_type]}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={JOB_STATUS_VARIANT[job.status]}>{JOB_STATUS_LABELS[job.status]}</Badge>
                    {job.public && (
                      <a
                        href={careerPath(job)}
                        target="_blank"
                        rel="noreferrer"
                        className="ml-2 inline-flex items-center gap-1 text-xs text-slate-500 underline"
                      >
                        Ansehen <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">
                    {[job.department_name, job.location_name].filter(Boolean).join(' · ') || '–'}
                  </TableCell>
                  <TableCell>{job.application_deadline ? formatDate(job.application_deadline) : '–'}</TableCell>
                  <TableCell>
                    <button type="button" className="text-sm underline" onClick={() => onShowApplications(job.id)}>
                      {job.application_count} ({job.open_count} offen)
                    </button>
                    {deletedSummary(job) && <div className="text-xs text-slate-400">Gelöscht: {deletedSummary(job)}</div>}
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">
                    {job.members.map((member) => member.name).join(', ') || '–'}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-right">
                    {canManage && (
                      <>
                        <Button variant="ghost" size="icon" aria-label={`${job.title} bearbeiten`} onClick={() => setEditing(job)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" aria-label={`${job.title} löschen`} onClick={() => void deleteJob(job)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {creating && <JobDialog job={null} open onClose={() => setCreating(false)} />}
      {editing && <JobDialog key={editing.id} job={editing} open onClose={() => setEditing(null)} />}
    </div>
  )
}
