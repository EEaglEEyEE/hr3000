import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useCareersQuery } from '../api/queries/recruiting'
import { EMPLOYMENT_TYPE_LABELS, careerPath } from '../components/recruiting/labels'
import { formatDate } from '../lib/format'

/** Rahmen der öffentlichen Karriereseite (ohne Anmeldung). */
export function CareersShell({ company, children }: { company?: string; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-2 px-4 py-4">
          <Link to="/karriere" className="text-lg font-semibold text-slate-900">
            {company ? `Karriere bei ${company}` : 'Karriere'}
          </Link>
        </div>
      </header>
      <main className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-6">{children}</main>
    </div>
  )
}

export function CareersPage() {
  const careers = useCareersQuery()
  if (careers.isLoading) {
    return (
      <CareersShell>
        <p className="text-sm text-slate-500">Lädt…</p>
      </CareersShell>
    )
  }
  if (!careers.data) {
    return (
      <CareersShell>
        <p className="text-sm text-slate-600">Diese Seite gibt es nicht.</p>
      </CareersShell>
    )
  }
  const { jobs, company_name: company } = careers.data
  return (
    <CareersShell company={company}>
      <h1 className="text-xl font-semibold text-slate-900">Offene Stellen</h1>
      {jobs.length === 0 && <p className="text-sm text-slate-600">Zurzeit sind keine Stellen ausgeschrieben.</p>}
      <ul className="flex flex-col gap-3">
        {jobs.map((job) => (
          <li key={job.id}>
            <Link
              to={careerPath(job)}
              className="flex flex-col gap-1 rounded-md border border-slate-200 bg-white p-4 hover:border-slate-400"
            >
              <span className="text-base font-medium text-slate-900">{job.title}</span>
              <span className="text-sm text-slate-600">
                {[EMPLOYMENT_TYPE_LABELS[job.employment_type], job.department, job.location].filter(Boolean).join(' · ')}
              </span>
              {job.application_deadline && (
                <span className="text-xs text-slate-500">Bewerbungsschluss: {formatDate(job.application_deadline)}</span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </CareersShell>
  )
}
