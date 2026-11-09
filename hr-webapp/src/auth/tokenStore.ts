const ACCESS_TOKEN_KEY = 'hr3000.access_token'
const REFRESH_TOKEN_KEY = 'hr3000.refresh_token'
// Bis zum Kontomodell (11/2026) gespeichert – wird beim An- und Abmelden entfernt.
const LEGACY_PRINCIPAL_TYPE_KEY = 'hr3000.principal_type'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  localStorage.removeItem(LEGACY_PRINCIPAL_TYPE_KEY)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(LEGACY_PRINCIPAL_TYPE_KEY)
  window.dispatchEvent(new Event('auth:logout'))
}

/** Liest den Payload eines JWT, ohne die Signatur zu prüfen – nur für
 * UI-Zwecke (z.B. "welcher Mitarbeiter bin ich", "habe ich Admin-Rechte"),
 * die eigentliche Autorisierung erfolgt in jedem Fall serverseitig bei jedem
 * Request frisch aus der Datenbank. */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const payloadBase64 = token.split('.')[1]
    const normalized = payloadBase64.replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(normalized)) as Record<string, unknown>
  } catch {
    return null
  }
}

export function decodeJwtSubject(token: string): string | null {
  const payload = decodeJwtPayload(token)
  const sub = payload?.sub
  return typeof sub === 'string' ? sub : null
}

interface TokenPair {
  access_token: string
  refresh_token: string
}

let refreshPromise: Promise<string | null> | null = null

/** Tauscht das Refresh-Token gegen ein neues Token-Paar. Parallele 401er
 * teilen sich denselben laufenden Refresh-Request statt jeweils eigene
 * Refresh-Requests zu feuern. */
export function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    return Promise.resolve(null)
  }

  if (!refreshPromise) {
    refreshPromise = doRefresh(refreshToken).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function doRefresh(refreshToken: string): Promise<string | null> {
  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (response.status === 401 || response.status === 403) {
      // Refresh-Token wirklich ungültig/abgelaufen -> abmelden.
      clearTokens()
      return null
    }
    if (!response.ok) {
      // Vorübergehender Fehler (z.B. 502 während eines Deployments): Sitzung behalten.
      return null
    }
    const body = (await response.json()) as TokenPair
    setTokens(body.access_token, body.refresh_token)
    return body.access_token
  } catch {
    // Netzwerkfehler: nicht abmelden, der nächste Versuch klappt vielleicht.
    return null
  }
}
