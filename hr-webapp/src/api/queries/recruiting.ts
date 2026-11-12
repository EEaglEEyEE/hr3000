import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../client'
import { authFetch, failure } from '../documents'
import type { components } from '../schema'

export type RecruitingAccess = components['schemas']['RecruitingAccessResponse']
export type Job = components['schemas']['JobResponse']
export type JobWrite = components['schemas']['JobWriteRequest']
export type TeamCandidate = components['schemas']['TeamCandidateResponse']
export type ApplicationItem = components['schemas']['ApplicationListItem']
export type ApplicationDetail = components['schemas']['ApplicationDetailResponse']
export type ApplicationCreate = components['schemas']['ApplicationCreateRequest']
export type ApplicationUpdate = components['schemas']['ApplicationUpdateRequest']
export type StageChange = components['schemas']['StageChangeRequest']
export type HireRequest = components['schemas']['HireRequest']
export type HireResult = components['schemas']['HireResponse']
export type Stage = ApplicationItem['stage']
export type JobStatus = Job['status']
export type EmploymentType = Job['employment_type']
export type RejectionReason = NonNullable<StageChange['rejection_reason']>
export type AttachmentKind = components['schemas']['AttachmentResponse']['kind']
export type Careers = components['schemas']['CareersResponse']
export type PublicJob = components['schemas']['PublicJobResponse']
export type PublicJobDetail = components['schemas']['PublicJobDetailResponse']

const KEY = ['recruiting'] as const

function useInvalidate() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: KEY })
}

function noContent(result: { error?: unknown; response: Response }) {
  if (result.error !== undefined) {
    const detail = result.error as { detail?: unknown; code?: string }
    throw new ApiError(result.response.status, detail.code, typeof detail.detail === 'string' ? detail.detail : 'Aktion fehlgeschlagen.')
  }
}

/** Unter ['features', …]: Änderungen an den Einstellungen laden Menü und Reiter neu. */
export function useRecruitingAccessQuery(enabled = true) {
  return useQuery({
    queryKey: ['features', 'recruiting'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/recruiting/access')),
    staleTime: 60_000,
  })
}

export function useJobsQuery(enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'jobs'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/recruiting/jobs')),
  })
}

export function useTeamCandidatesQuery(enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'team-candidates'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/recruiting/team-candidates')),
  })
}

export function useSaveJobMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async ({ id, payload }: { id?: number; payload: JobWrite }) =>
      id === undefined
        ? unwrap(await apiClient.POST('/recruiting/jobs', { body: payload }))
        : unwrap(await apiClient.PUT('/recruiting/jobs/{job_id}', { params: { path: { job_id: id } }, body: payload })),
    onSuccess: invalidate,
  })
}

export function useDeleteJobMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (id: number) =>
      noContent(await apiClient.DELETE('/recruiting/jobs/{job_id}', { params: { path: { job_id: id } } })),
    onSuccess: invalidate,
  })
}

export function useApplicationsQuery(jobId?: number) {
  return useQuery({
    queryKey: [...KEY, 'applications', jobId ?? null],
    queryFn: async () =>
      unwrap(await apiClient.GET('/recruiting/applications', { params: { query: jobId ? { job_id: jobId } : {} } })),
  })
}

export function useDueForDeletionQuery(enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'due'],
    enabled,
    queryFn: async () =>
      unwrap(await apiClient.GET('/recruiting/applications/due-for-deletion', { params: { query: { within_days: 30 } } })),
  })
}

export function useApplicationQuery(id: number | null) {
  return useQuery({
    queryKey: [...KEY, 'application', id],
    enabled: id !== null,
    queryFn: async () =>
      unwrap(await apiClient.GET('/recruiting/applications/{application_id}', { params: { path: { application_id: id! } } })),
  })
}

export function useCreateApplicationMutation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (payload: ApplicationCreate) => unwrap(await apiClient.POST('/recruiting/applications', { body: payload })),
    onSuccess: invalidate,
  })
}

/** Alle Änderungen an einer Bewerbung, die die Detailansicht zurückgibt. */
export function useApplicationActions(id: number) {
  const invalidate = useInvalidate()
  const path = { params: { path: { application_id: id } } }
  const options = { onSuccess: invalidate }
  return {
    update: useMutation({
      mutationFn: async (body: ApplicationUpdate) =>
        unwrap(await apiClient.PATCH('/recruiting/applications/{application_id}', { ...path, body })),
      ...options,
    }),
    stage: useMutation({
      mutationFn: async (body: StageChange) =>
        unwrap(await apiClient.POST('/recruiting/applications/{application_id}/stage', { ...path, body })),
      ...options,
    }),
    addNote: useMutation({
      mutationFn: async (body: string) =>
        unwrap(await apiClient.POST('/recruiting/applications/{application_id}/notes', { ...path, body: { body } })),
      ...options,
    }),
    deleteNote: useMutation({
      mutationFn: async (noteId: number) =>
        unwrap(
          await apiClient.DELETE('/recruiting/applications/{application_id}/notes/{note_id}', {
            params: { path: { application_id: id, note_id: noteId } },
          }),
        ),
      ...options,
    }),
    rate: useMutation({
      mutationFn: async (body: { score: number; comment?: string | null }) =>
        unwrap(await apiClient.PUT('/recruiting/applications/{application_id}/rating', { ...path, body })),
      ...options,
    }),
    unrate: useMutation({
      mutationFn: async () => unwrap(await apiClient.DELETE('/recruiting/applications/{application_id}/rating', path)),
      ...options,
    }),
    upload: useMutation({
      mutationFn: async ({ file, kind }: { file: File; kind: AttachmentKind }) => {
        const form = new FormData()
        form.append('file', file)
        form.append('kind', kind)
        const response = await authFetch(`/api/recruiting/applications/${id}/attachments`, { method: 'POST', body: form })
        if (!response.ok) throw await failure(response, 'Hochladen fehlgeschlagen.')
        return (await response.json()) as ApplicationDetail
      },
      ...options,
    }),
    deleteAttachment: useMutation({
      mutationFn: async (attachmentId: number) =>
        unwrap(
          await apiClient.DELETE('/recruiting/applications/{application_id}/attachments/{attachment_id}', {
            params: { path: { application_id: id, attachment_id: attachmentId } },
          }),
        ),
      ...options,
    }),
    remove: useMutation({
      mutationFn: async () => noContent(await apiClient.DELETE('/recruiting/applications/{application_id}', path)),
      ...options,
    }),
    hire: useMutation({
      mutationFn: async (body: HireRequest) =>
        unwrap(await apiClient.POST('/recruiting/applications/{application_id}/hire', { ...path, body })),
      onSuccess: () => {
        invalidate()
      },
    }),
  }
}

/** Anhang ansehen (neuer Tab) oder herunterladen – mit Anmeldung, daher über einen Blob. */
export async function openAttachment(applicationId: number, attachmentId: number, filename: string, inline: boolean) {
  const url = `/api/recruiting/applications/${applicationId}/attachments/${attachmentId}/download${inline ? '?inline=true' : ''}`
  const response = await authFetch(url)
  if (!response.ok) throw await failure(response, 'Der Anhang konnte nicht geladen werden.')
  const blobUrl = URL.createObjectURL(await response.blob())
  if (inline) {
    window.open(blobUrl, '_blank', 'noopener')
  } else {
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename
    link.click()
  }
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000)
}

// --- Karriereseite (ohne Anmeldung) ---

export function useCareersQuery() {
  return useQuery({
    queryKey: ['careers'],
    queryFn: async () => unwrap(await apiClient.GET('/public/careers')),
  })
}

export function useCareerJobQuery(jobId: number | null) {
  return useQuery({
    queryKey: ['careers', jobId],
    enabled: jobId !== null,
    queryFn: async () => unwrap(await apiClient.GET('/public/careers/jobs/{job_id}', { params: { path: { job_id: jobId! } } })),
  })
}

export interface PublicApplicationInput {
  firstName: string
  lastName: string
  email: string
  phone: string
  coverLetter: string
  salaryExpectation: string
  privacyAcknowledged: boolean
  talentPool: boolean
  /** Honeypot – für Menschen unsichtbar */
  website: string
  cv: File | null
  attachments: File[]
}

export function useApplyMutation(jobId: number) {
  return useMutation({
    mutationFn: async (input: PublicApplicationInput) => {
      const form = new FormData()
      form.append('first_name', input.firstName)
      form.append('last_name', input.lastName)
      form.append('email', input.email)
      if (input.phone) form.append('phone', input.phone)
      if (input.coverLetter) form.append('cover_letter', input.coverLetter)
      if (input.salaryExpectation) form.append('salary_expectation', input.salaryExpectation)
      form.append('privacy_acknowledged', String(input.privacyAcknowledged))
      form.append('talent_pool', String(input.talentPool))
      if (input.website) form.append('website', input.website)
      if (input.cv) form.append('cv', input.cv)
      for (const file of input.attachments) form.append('attachments', file)
      // Ohne Anmeldung: bewusst kein Token mitschicken
      const response = await fetch(`/api/public/careers/jobs/${jobId}/applications`, { method: 'POST', body: form })
      if (!response.ok) throw await failure(response, 'Die Bewerbung konnte nicht gesendet werden.')
      return true
    },
  })
}
