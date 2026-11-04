import { ApiError } from './client'

interface TokenPair {
  access_token: string
  refresh_token: string
}

/** POST ohne Anmeldung; wirft ApiError mit Status und Fehlercode (z.B. EMAIL_NOT_VERIFIED). */
async function postPublic<T>(endpoint: string, body: unknown, fallback: string): Promise<T> {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as { detail?: unknown; code?: string } | null
    const detail = typeof error?.detail === 'string' ? error.detail : fallback
    throw new ApiError(response.status, error?.code, detail)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function hrLogin(email: string, password: string): Promise<TokenPair> {
  return postPublic('/api/auth/hr/login', { email, password }, 'Login fehlgeschlagen.')
}

export function employeeLogin(email: string, password: string): Promise<TokenPair> {
  return postPublic('/api/auth/employee/login', { email, password }, 'Login fehlgeschlagen.')
}

/** "Passwort vergessen": Link per E-Mail anfordern – antwortet immer gleich (kein Hinweis, ob es das Konto gibt). */
export function requestPasswordReset(email: string): Promise<{ detail: string }> {
  return postPublic('/api/auth/password-reset/request', { email }, 'Das hat nicht geklappt.')
}

/** Neues Passwort mit dem Token aus dem E-Mail-Link setzen. */
export function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  return postPublic('/api/auth/password-reset/confirm', { token, new_password: newPassword }, 'Das hat nicht geklappt.')
}
