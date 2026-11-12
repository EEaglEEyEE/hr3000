import { useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { login as loginRequest } from '../api/auth'
import { clearTokens, decodeJwtPayload, getAccessToken, getRefreshToken, setTokens } from './tokenStore'
import { AREAS, type Perms } from '../lib/access'

interface AuthState {
  isAuthenticated: boolean
  /** Mitarbeiter des Kontos („Mein Bereich“), sonst null (reines Verwaltungskonto). */
  employeeId: number | null
  /** Konto mit Verwaltungsrolle – bestimmt, ob die volle Webapp oder nur „Mein Bereich“ erscheint. */
  hasHrAccess: boolean
  /** Rolle ADMIN. */
  isAdmin: boolean
  /** ADMIN, HR oder SUPER_ADMIN – im Gegensatz zu SUPERVISOR nicht auf eigene
   * Teams beschränkt (darf z.B. Arbeitszeitmodelle ändern). */
  isFullHr: boolean
  /** Berechtigung „Vergütung & Lohn-Export“: Admins immer, HR mit Freigabe (Token-Claim payroll).
   * Nur für die Anzeige – das Backend prüft selbst. */
  canPayroll: boolean
  /** Rolle SUPER_ADMIN – plattformweit, keinem Mandanten zugeordnet. Nur über den
   * Super-Admin-Hostname erreichbar. */
  isSuperAdmin: boolean
  /** Eigene Rolle (Token-Claim perms): Stufe je Bereich; null = keine eigene Rolle (volle Rolle). */
  perms: Perms | null
}

/** Nach dem Passwort noch ein Schritt: Code eingeben bzw. (Pflicht) Zwei-Faktor-Anmeldung einrichten. */
export interface TwoFactorStep {
  kind: 'required' | 'setup'
  challengeToken: string
}

interface AuthContextValue extends AuthState {
  /** Ein Login für alle Konten; was man sieht, richtet sich nach Rolle und Mitarbeiter des Kontos.
   * Liefert den nächsten Schritt, wenn die Zwei-Faktor-Anmeldung noch fehlt (sonst null = angemeldet). */
  login: (email: string, password: string) => Promise<TwoFactorStep | null>
  logout: () => void
  /** Nach "Passwort ändern": neue Tokens derselben Person übernehmen (alte sind ungültig). */
  updateTokens: (accessToken: string, refreshToken: string) => void
}

const SIGNED_OUT: AuthState = {
  isAuthenticated: false,
  employeeId: null,
  hasHrAccess: false,
  isAdmin: false,
  isFullHr: false,
  canPayroll: false,
  isSuperAdmin: false,
  perms: null,
}

const LEVELS = ['NONE', 'VIEW', 'EDIT']

/** Nur bekannte Bereiche/Stufen übernehmen; ein Konto MIT eigener Rolle bleibt eingeschränkt (leer = nichts). */
function readPerms(raw: unknown): Perms | null {
  if (raw === null || raw === undefined || typeof raw !== 'object' || Array.isArray(raw)) return null
  const perms: Perms = {}
  for (const area of AREAS) {
    const value = (raw as Record<string, unknown>)[area]
    perms[area] = typeof value === 'string' && LEVELS.includes(value) ? (value as Perms[typeof area]) : 'NONE'
  }
  return perms
}

const KNOWN_ROLES = ['ADMIN', 'HR', 'SUPERVISOR', 'SUPER_ADMIN']

/** Rechte aus dem Token (claims role, emp, payroll, perms) – nur für die Anzeige, das Backend prüft selbst. */
function readAuthState(): AuthState {
  if (getRefreshToken() === null) return SIGNED_OUT
  const token = getAccessToken()
  const payload = token ? decodeJwtPayload(token) : null
  const role = typeof payload?.role === 'string' && KNOWN_ROLES.includes(payload.role) ? payload.role : null
  const employeeId = typeof payload?.emp === 'number' ? payload.emp : null
  return {
    isAuthenticated: true,
    employeeId,
    hasHrAccess: role !== null,
    isAdmin: role === 'ADMIN',
    isFullHr: role === 'ADMIN' || role === 'HR' || role === 'SUPER_ADMIN',
    canPayroll: payload?.payroll === true || role === 'ADMIN',
    isSuperAdmin: role === 'SUPER_ADMIN',
    perms: role === 'HR' ? readPerms(payload?.perms) : null,
  }
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [state, setState] = useState<AuthState>(readAuthState)

  useEffect(() => {
    const handleLogout = () => {
      // Gecachte Daten der abgemeldeten Person dürfen dem nächsten Login nicht angezeigt werden.
      queryClient.clear()
      setState(SIGNED_OUT)
    }
    window.addEventListener('auth:logout', handleLogout)
    return () => window.removeEventListener('auth:logout', handleLogout)
  }, [queryClient])

  async function login(email: string, password: string): Promise<TwoFactorStep | null> {
    const result = await loginRequest(email, password)
    if (result.two_factor && result.challenge_token) {
      return { kind: result.two_factor, challengeToken: result.challenge_token }
    }
    if (!result.access_token || !result.refresh_token) throw new Error('Unerwartete Antwort beim Anmelden.')
    setTokens(result.access_token, result.refresh_token)
    setState(readAuthState())
    return null
  }

  function updateTokens(accessToken: string, refreshToken: string) {
    setTokens(accessToken, refreshToken)
    setState(readAuthState())
  }

  function logout() {
    clearTokens()
    setState(SIGNED_OUT)
  }

  return <AuthContext.Provider value={{ ...state, login, logout, updateTokens }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth muss innerhalb von AuthProvider verwendet werden.')
  }
  return ctx
}
