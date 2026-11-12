/** Öffentliche Meldeseite des Hinweisgebersystems (/hinweis). Bewusst blankes fetch() statt apiClient:
 * Dieser hängt das Anmelde-Token an – eine Meldung soll aber nie mit einem Konto verbunden werden,
 * auch nicht, wenn die Person im selben Browser angemeldet ist. Zugangsdaten stehen immer im Rumpf. */
import { ApiError } from './client'
import type { components } from './schema'

export type WhistleInfo = components['schemas']['WhistleInfoResponse']
export type WhistleReport = components['schemas']['WhistleReportCreate']
export type WhistleCreated = components['schemas']['WhistleReportCreated']
export type WhistlePublicCase = components['schemas']['WhistlePublicCase']
export interface WhistleAccess {
  case_number: string
  access_code: string
}

const BASE = '/api/public/whistle'

async function parse<T>(response: Response, fallback: string): Promise<T> {
  const body = (await response.json().catch(() => null)) as (T & { detail?: unknown; code?: string }) | null
  if (!response.ok) {
    const message = typeof body?.detail === 'string' ? body.detail : fallback
    throw new ApiError(response.status, body?.code, message)
  }
  return body as T
}

function post<T>(path: string, body: unknown, fallback: string): Promise<T> {
  return fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'omit',
    body: JSON.stringify(body),
  }).then((response) => parse<T>(response, fallback))
}

/** null = Hinweisgebersystem ist in dieser Firma nicht eingerichtet. */
export async function fetchWhistleInfo(): Promise<WhistleInfo | null> {
  const response = await fetch(`${BASE}/info`, { credentials: 'omit' })
  if (response.status === 404) return null
  return parse<WhistleInfo>(response, 'Die Seite konnte nicht geladen werden.')
}

export function submitWhistleReport(report: WhistleReport): Promise<WhistleCreated> {
  return post('/reports', report, 'Die Meldung konnte nicht gesendet werden.')
}

export function fetchWhistleCase(access: WhistleAccess): Promise<WhistlePublicCase> {
  return post('/status', access, 'Der Stand konnte nicht abgefragt werden.')
}

export function sendWhistleMessage(access: WhistleAccess, body: string): Promise<WhistlePublicCase> {
  return post('/messages', { ...access, body }, 'Die Nachricht konnte nicht gesendet werden.')
}

export async function uploadWhistleAttachment(access: WhistleAccess, file: File): Promise<WhistlePublicCase> {
  const form = new FormData()
  form.append('case_number', access.case_number)
  form.append('access_code', access.access_code)
  form.append('file', file)
  const response = await fetch(`${BASE}/attachments`, { method: 'POST', credentials: 'omit', body: form })
  return parse<WhistlePublicCase>(response, 'Die Datei konnte nicht hochgeladen werden.')
}
