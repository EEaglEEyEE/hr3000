import { useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { employeeLogin, hrLogin } from '../api/auth'
import {
  clearTokens,
  decodeJwtPayload,
  decodeJwtSubject,
  getAccessToken,
  getPrincipalType,
  getRefreshToken,
  setTokens,
  type PrincipalType,
} from './tokenStore'

interface AuthContextValue {
  isAuthenticated: boolean
  principalType: PrincipalType | null
  /** Nur gesetzt, wenn principalType === 'employee' (Self-Service oder
   * Mitarbeiter mit hr_role). */
  employeeId: number | null
  /** true für jeden HrUser-Account UND für Mitarbeiter mit gesetztem
   * hr_role – bestimmt, ob die volle HR-Webapp oder nur "Mein Bereich"
   * (read-only) gezeigt wird. */
  hasHrAccess: boolean
  /** HrUser.role === ADMIN bzw. Employee.hr_role === ADMIN. */
  isAdmin: boolean
  /** ADMIN, HR oder SUPER_ADMIN – im Gegensatz zu SUPERVISOR nicht auf eigene
   * Teams beschränkt (darf z.B. Arbeitszeitmodelle ändern). */
  isFullHr: boolean
  /** HrUser.role === SUPER_ADMIN – plattformweit, keinem Mandanten
   * zugeordnet. Nur über den Super-Admin-Hostname erreichbar. */
  isSuperAdmin: boolean
  /** Ein Login-Formular: probiert HR-Zugangsdaten, bei Fehlschlag
   * Mitarbeiter-Zugangsdaten – der Zugang richtet sich nach den
   * hinterlegten Berechtigungen, nicht nach einer manuellen Auswahl. */
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function deriveEmployeeId(principalType: PrincipalType | null): number | null {
  if (principalType !== 'employee') return null
  const token = getAccessToken()
  if (!token) return null
  const subject = decodeJwtSubject(token)
  return subject ? Number(subject) : null
}

function deriveEmployeeHrRole(): string | null {
  const token = getAccessToken()
  if (!token) return null
  const payload = decodeJwtPayload(token)
  const hrRole = payload?.hr_role
  return typeof hrRole === 'string' ? hrRole : null
}

function deriveHasHrAccess(principalType: PrincipalType | null): boolean {
  if (principalType === 'hr') return true
  if (principalType === 'employee') return deriveEmployeeHrRole() !== null
  return false
}

function deriveIsAdmin(principalType: PrincipalType | null): boolean {
  const token = getAccessToken()
  if (!token) return false
  const payload = decodeJwtPayload(token)
  if (!payload) return false
  const roleClaim = principalType === 'hr' ? payload.role : payload.hr_role
  return roleClaim === 'ADMIN'
}

function deriveIsFullHr(principalType: PrincipalType | null): boolean {
  const token = getAccessToken()
  if (!token) return false
  const payload = decodeJwtPayload(token)
  if (!payload) return false
  const roleClaim = principalType === 'hr' ? payload.role : payload.hr_role
  return roleClaim === 'ADMIN' || roleClaim === 'HR' || roleClaim === 'SUPER_ADMIN'
}

function deriveIsSuperAdmin(principalType: PrincipalType | null): boolean {
  const token = getAccessToken()
  if (!token) return false
  const payload = decodeJwtPayload(token)
  if (!payload) return false
  const roleClaim = principalType === 'hr' ? payload.role : payload.hr_role
  return roleClaim === 'SUPER_ADMIN'
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [isAuthenticated, setIsAuthenticated] = useState(() => getRefreshToken() !== null)
  const [principalType, setPrincipalType] = useState<PrincipalType | null>(() => getPrincipalType())
  const [employeeId, setEmployeeId] = useState<number | null>(() => deriveEmployeeId(getPrincipalType()))
  const [hasHrAccess, setHasHrAccess] = useState(() => deriveHasHrAccess(getPrincipalType()))
  const [isAdmin, setIsAdmin] = useState(() => deriveIsAdmin(getPrincipalType()))
  const [isFullHr, setIsFullHr] = useState(() => deriveIsFullHr(getPrincipalType()))
  const [isSuperAdmin, setIsSuperAdmin] = useState(() => deriveIsSuperAdmin(getPrincipalType()))

  useEffect(() => {
    const handleLogout = () => {
      // Gecachte Daten der abgemeldeten Person dürfen dem nächsten Login nicht angezeigt werden.
      queryClient.clear()
      setIsAuthenticated(false)
      setPrincipalType(null)
      setEmployeeId(null)
      setHasHrAccess(false)
      setIsAdmin(false)
      setIsFullHr(false)
      setIsSuperAdmin(false)
    }
    window.addEventListener('auth:logout', handleLogout)
    return () => window.removeEventListener('auth:logout', handleLogout)
  }, [queryClient])

  async function login(email: string, password: string) {
    try {
      const tokens = await hrLogin(email, password)
      setTokens(tokens.access_token, tokens.refresh_token, 'hr')
      setIsAuthenticated(true)
      setPrincipalType('hr')
      setEmployeeId(null)
      setHasHrAccess(true)
      setIsAdmin(deriveIsAdmin('hr'))
      setIsFullHr(deriveIsFullHr('hr'))
      setIsSuperAdmin(deriveIsSuperAdmin('hr'))
      return
    } catch {
      // Kein HR-Zugang mit diesen Daten – als Mitarbeiter-Login versuchen.
    }

    const tokens = await employeeLogin(email, password)
    setTokens(tokens.access_token, tokens.refresh_token, 'employee')
    setIsAuthenticated(true)
    setPrincipalType('employee')
    setEmployeeId(deriveEmployeeId('employee'))
    setHasHrAccess(deriveHasHrAccess('employee'))
    setIsAdmin(deriveIsAdmin('employee'))
    setIsFullHr(deriveIsFullHr('employee'))
    setIsSuperAdmin(false)
  }

  function logout() {
    clearTokens()
    setIsAuthenticated(false)
    setPrincipalType(null)
    setEmployeeId(null)
    setHasHrAccess(false)
    setIsAdmin(false)
    setIsFullHr(false)
    setIsSuperAdmin(false)
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        principalType,
        employeeId,
        hasHrAccess,
        isAdmin,
        isFullHr,
        isSuperAdmin,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth muss innerhalb von AuthProvider verwendet werden.')
  }
  return ctx
}
