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

export interface LoginResult {
  access_token: string | null
  refresh_token: string | null
  /** "required": Code aus der App eingeben; "setup": Zwei-Faktor-Anmeldung ist Pflicht und erst einzurichten */
  two_factor: 'required' | 'setup' | null
  challenge_token: string | null
}

export interface TwoFactorSetup {
  secret: string
  otpauth_uri: string
}

export interface TwoFactorEnabled extends TokenPair {
  recovery_codes: string[]
}

/** Ein Login für alle Konten (Verwaltung, Mitarbeiter, Super-Admin auf dem admin.-Host). */
export function login(email: string, password: string): Promise<LoginResult> {
  return postPublic('/api/auth/login', { email, password }, 'Login fehlgeschlagen.')
}

/** Zweiter Schritt: Code aus der Authenticator-App oder ein Wiederherstellungscode. */
export function loginTwoFactor(challengeToken: string, code: string): Promise<TokenPair> {
  return postPublic('/api/auth/login/2fa', { challenge_token: challengeToken, code }, 'Der Code stimmt nicht.')
}

/** Pflicht-Einrichtung direkt beim Login (mit dem Challenge-Token statt einer Sitzung). */
export function setupTwoFactorAtLogin(challengeToken: string): Promise<TwoFactorSetup> {
  return postPublic('/api/auth/2fa/setup', { challenge_token: challengeToken }, 'Das hat nicht geklappt.')
}

export function enableTwoFactorAtLogin(challengeToken: string, code: string): Promise<TwoFactorEnabled> {
  return postPublic('/api/auth/2fa/enable', { challenge_token: challengeToken, code }, 'Der Code stimmt nicht.')
}

/** "Passwort vergessen": Link per E-Mail anfordern – antwortet immer gleich (kein Hinweis, ob es das Konto gibt). */
export function requestPasswordReset(email: string): Promise<{ detail: string }> {
  return postPublic('/api/auth/password-reset/request', { email }, 'Das hat nicht geklappt.')
}

/** Neues Passwort mit dem Token aus dem E-Mail-Link setzen. */
export function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  return postPublic('/api/auth/password-reset/confirm', { token, new_password: newPassword }, 'Das hat nicht geklappt.')
}
