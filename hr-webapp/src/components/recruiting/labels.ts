import type { BadgeProps } from '../ui/badge'
import type { EmploymentType, JobStatus, RejectionReason, Stage } from '../../api/queries/recruiting'

export const STAGES: Stage[] = ['NEW', 'SCREENING', 'INTERVIEW', 'OFFER', 'HIRED', 'REJECTED', 'WITHDRAWN']

export const STAGE_LABELS: Record<Stage, string> = {
  NEW: 'Neu',
  SCREENING: 'Sichtung',
  INTERVIEW: 'Interview',
  OFFER: 'Angebot',
  HIRED: 'Eingestellt',
  REJECTED: 'Abgelehnt',
  WITHDRAWN: 'Zurückgezogen',
}

export const STAGE_VARIANT: Record<Stage, BadgeProps['variant']> = {
  NEW: 'info',
  SCREENING: 'violet',
  INTERVIEW: 'teal',
  OFFER: 'orange',
  HIRED: 'success',
  REJECTED: 'danger',
  WITHDRAWN: 'default',
}

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  DRAFT: 'Entwurf',
  PUBLISHED: 'Veröffentlicht',
  CLOSED: 'Geschlossen',
}

export const JOB_STATUS_VARIANT: Record<JobStatus, BadgeProps['variant']> = {
  DRAFT: 'default',
  PUBLISHED: 'success',
  CLOSED: 'warning',
}

export const EMPLOYMENT_TYPE_LABELS: Record<EmploymentType, string> = {
  FULL_TIME: 'Vollzeit',
  PART_TIME: 'Teilzeit',
  MINI_JOB: 'Minijob',
  FIXED_TERM: 'Befristet',
  APPRENTICESHIP: 'Ausbildung',
  INTERNSHIP: 'Praktikum',
  WORKING_STUDENT: 'Werkstudent',
  FREELANCE: 'Freie Mitarbeit',
}

export const REJECTION_REASON_LABELS: Record<RejectionReason, string> = {
  QUALIFICATION: 'Qualifikation passt nicht',
  EXPERIENCE: 'Zu wenig Erfahrung',
  SALARY: 'Gehaltsvorstellung',
  POSITION_FILLED: 'Stelle anderweitig besetzt',
  NO_RESPONSE: 'Keine Rückmeldung',
  OTHER: 'Sonstiges',
}

export const SOURCE_LABELS: Record<'CAREER_PAGE' | 'MANUAL', string> = {
  CAREER_PAGE: 'Karriereseite',
  MANUAL: 'Manuell erfasst',
}

/** Adresse der Stelle auf der Karriereseite (/karriere/12-sachbearbeiter-in). */
export function careerPath(job: { id: number; slug: string }): string {
  return `/karriere/${job.id}-${job.slug}`
}

/** Stellen-ID aus dem Pfadteil „12-sachbearbeiter-in“; null bei ungültiger Angabe. */
export function jobIdFromParam(param: string | undefined): number | null {
  const match = /^(\d+)(?:-|$)/.exec(param ?? '')
  if (!match) return null
  const id = Number(match[1])
  return Number.isSafeInteger(id) && id > 0 ? id : null
}

export const SELECT_CLASS = 'h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm'
export const TEXTAREA_CLASS = 'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm'
