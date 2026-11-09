import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from './client'
import type { components } from './schema'
import { getAccessToken, refreshAccessToken } from '../auth/tokenStore'

export type EmployeeDocument = components['schemas']['DocumentResponse']
export type DocumentCategory = EmployeeDocument['category']
export type DocumentUpdateRequest = components['schemas']['DocumentUpdateRequest']

/** fetch() mit Bearer-Token und einmaligem Refresh bei 401. Für Upload/Download, weil
 * der apiClient den Body für den Retry als Text zwischenspeichert (kaputt bei multipart). */
export async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const send = (token: string | null) =>
    fetch(url, { ...init, headers: { ...(init.headers ?? {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) } })
  let response = await send(getAccessToken())
  if (response.status === 401) {
    const token = await refreshAccessToken()
    if (token) response = await send(token)
  }
  return response
}

export async function failure(response: Response, fallback: string): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown; code?: string } | null
  const message = typeof body?.detail === 'string' ? body.detail : fallback
  return new ApiError(response.status, body?.code, message)
}

export interface UploadDocumentInput {
  file: File
  category: DocumentCategory
  title: string
  employeeVisible: boolean
  confidential: boolean
  retentionUntil: string
  /** Eigene Kategorie (dann category = OTHER) */
  categoryId?: number | null
}

export type DocumentCategoryDefinition = components['schemas']['DocumentCategoryResponse']

export function useDocumentCategoriesQuery(enabled = true) {
  return useQuery({
    queryKey: ['document-categories'],
    enabled,
    queryFn: async () => unwrap(await apiClient.GET('/document-categories')),
  })
}

export function useCreateDocumentCategoryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: components['schemas']['DocumentCategoryRequest']) =>
      unwrap(await apiClient.POST('/document-categories', { body: payload })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['document-categories'] }),
  })
}

export function useUpdateDocumentCategoryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: components['schemas']['DocumentCategoryUpdateRequest'] }) =>
      unwrap(await apiClient.PATCH('/document-categories/{category_id}', { params: { path: { category_id: id } }, body: payload })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['document-categories'] }),
  })
}

/** Mitarbeiter lädt selbst in eine freigegebene Kategorie hoch („Mein Bereich“ → „Dokumente“). */
export function useUploadOwnDocumentMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      file,
      categoryId,
      title,
      checklistItemId,
    }: {
      file: File
      categoryId: number
      title: string
      checklistItemId?: number
    }) => {
      const form = new FormData()
      form.append('file', file)
      form.append('category_id', String(categoryId))
      form.append('title', title)
      if (checklistItemId) form.append('checklist_item_id', String(checklistItemId))
      const response = await authFetch('/api/me/documents', { method: 'POST', body: form })
      if (!response.ok) throw await failure(response, 'Upload fehlgeschlagen.')
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'documents'] })
      void queryClient.invalidateQueries({ queryKey: ['my-checklist-items'] })
    },
  })
}

export function useDocumentsQuery(employeeId: number) {
  return useQuery({
    queryKey: ['employees', employeeId, 'documents'],
    queryFn: async () =>
      unwrap(await apiClient.GET('/employees/{employee_id}/documents', { params: { path: { employee_id: employeeId } } })),
  })
}

export function useUploadDocumentMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: UploadDocumentInput) => {
      const form = new FormData()
      form.append('file', input.file)
      form.append('category', input.category)
      form.append('title', input.title)
      form.append('employee_visible', String(input.employeeVisible))
      form.append('confidential', String(input.confidential))
      if (input.retentionUntil) form.append('retention_until', input.retentionUntil)
      if (input.categoryId) form.append('category_id', String(input.categoryId))
      const response = await authFetch(`/api/employees/${employeeId}/documents`, { method: 'POST', body: form })
      if (!response.ok) throw await failure(response, 'Upload fehlgeschlagen.')
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'documents'] }),
  })
}

export function useUpdateDocumentMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ documentId, payload }: { documentId: number; payload: DocumentUpdateRequest }) =>
      unwrap(
        await apiClient.PATCH('/employees/{employee_id}/documents/{document_id}', {
          params: { path: { employee_id: employeeId, document_id: documentId } },
          body: payload,
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'documents'] }),
  })
}

export function useDeleteDocumentMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (documentId: number) => {
      const result = await apiClient.DELETE('/employees/{employee_id}/documents/{document_id}', {
        params: { path: { employee_id: employeeId, document_id: documentId } },
      })
      if (result.error !== undefined) {
        const detail = result.error as { detail?: string; code?: string }
        throw new ApiError(result.response.status, detail.code, detail.detail ?? 'Löschen fehlgeschlagen.')
      }
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'documents'] }),
  })
}

export async function downloadDocument(employeeId: number, document_: EmployeeDocument): Promise<void> {
  const response = await authFetch(`/api/employees/${employeeId}/documents/${document_.id}/download`)
  if (!response.ok) throw await failure(response, 'Download fehlgeschlagen.')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = document_.original_filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/** Öffnet ein PDF der API (mit Anmeldung) in einem neuen Tab – Druckansicht. Das Fenster wird
 * sofort geöffnet (sonst blockt der Popup-Blocker), der Inhalt folgt nach dem Laden. */
export async function openPdfInNewTab(path: string): Promise<void> {
  const win = window.open('', '_blank')
  if (win) win.document.title = 'Bericht wird erstellt…'
  try {
    const response = await authFetch(`/api${path}`)
    if (!response.ok) throw await failure(response, 'Bericht konnte nicht erstellt werden.')
    const url = URL.createObjectURL(await response.blob())
    if (win) {
      win.location.href = url
    } else {
      window.location.href = url
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (err) {
    win?.close()
    throw err
  }
}

export type DocumentTemplate = components['schemas']['DocumentTemplateResponse']
export type DocumentTemplateRequest = components['schemas']['DocumentTemplateRequest']

export function useDocumentTemplatesQuery() {
  return useQuery({
    queryKey: ['document-templates'],
    queryFn: async () => unwrap(await apiClient.GET('/document-templates')),
  })
}

export function usePlaceholdersQuery() {
  return useQuery({
    queryKey: ['document-template-placeholders'],
    queryFn: async () => unwrap(await apiClient.GET('/document-templates/placeholders')),
    staleTime: Infinity,
  })
}

export function useSaveDocumentTemplateMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id?: number; payload: DocumentTemplateRequest & { archived?: boolean } }) =>
      id
        ? unwrap(await apiClient.PATCH('/document-templates/{template_id}', { params: { path: { template_id: id } }, body: { ...payload, clear_category_id: payload.category_id == null } }))
        : unwrap(await apiClient.POST('/document-templates', { body: payload })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['document-templates'] }),
  })
}

export function useGenerateFromTemplateMutation(employeeId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ templateId, title }: { templateId: number; title?: string }) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/documents/from-template', {
          params: { path: { employee_id: employeeId } },
          body: { template_id: templateId, title: title || null },
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees', employeeId, 'documents'] }),
  })
}

/** Vorschau als PDF in einem neuen Tab (ohne Ablage). */
export async function previewTemplate(employeeId: number, templateId: number): Promise<void> {
  const response = await authFetch(`/api/employees/${employeeId}/document-templates/${templateId}/preview`)
  if (!response.ok) throw await failure(response, 'Vorschau fehlgeschlagen.')
  const url = URL.createObjectURL(await response.blob())
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
