/** Hilfen für Komponententests: Anmeldung per Test-Token, ein Ersatz für die API und ein
 * Render-Wrapper mit Query-Client, Anmeldung und Router – ohne laufenden Server. */
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { apiClient } from '../api/client'
import { AuthProvider } from '../auth/AuthContext'

type Perms = Record<string, 'NONE' | 'VIEW' | 'EDIT'>
type Login =
  | { kind: 'hr'; role: 'SUPER_ADMIN' | 'ADMIN' | 'HR' | 'SUPERVISOR'; payroll?: boolean; perms?: Perms }
  | { kind: 'employee'; employeeId: number; hrRole?: 'ADMIN' | 'HR' | 'SUPERVISOR'; payroll?: boolean; perms?: Perms }

function base64Url(value: object): string {
  return btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Unsigniertes Test-Token – die Oberfläche liest daraus nur Rolle und Mitarbeiter-ID. */
export function fakeJwt(payload: Record<string, unknown>): string {
  return `${base64Url({ alg: 'none', typ: 'JWT' })}.${base64Url({ exp: 4102444800, ...payload })}.test`
}

export function loginAs(login: Login): void {
  // Ein Konto: Rolle (Verwaltung) und/oder Mitarbeiter (emp), wie im echten Token
  const payload =
    login.kind === 'hr'
      ? {
          sub: '1',
          type: 'account_access',
          role: login.role,
          emp: null,
          ...(login.payroll ? { payroll: true } : {}),
          ...(login.perms ? { perms: login.perms } : {}),
        }
      : {
          sub: '2',
          type: 'account_access',
          role: login.hrRole ?? null,
          emp: login.employeeId,
          ...(login.payroll ? { payroll: true } : {}),
          ...(login.perms ? { perms: login.perms } : {}),
        }
  localStorage.setItem('hr3000.access_token', fakeJwt(payload))
  localStorage.setItem('hr3000.refresh_token', fakeJwt(payload))
}

/** Fehlerantwort des Servers im Format {detail, code}. */
export class ApiFailure {
  status: number
  code: string
  detail: string
  constructor(status: number, code: string, detail: string) {
    this.status = status
    this.code = code
    this.detail = detail
  }
}

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
type RouteValue = unknown | ((init: ApiInit) => unknown)
export interface ApiInit {
  params?: { path?: Record<string, unknown>; query?: Record<string, unknown> }
  body?: unknown
}
export interface ApiCall {
  method: Method
  path: string
  init: ApiInit
}

/** Ersetzt apiClient.GET/POST/… : Schlüssel ist "METHODE /pfad/{platzhalter}" wie im Code.
 * Ein Wert ist die Antwort, eine Funktion berechnet sie (auch asynchron), ApiFailure liefert
 * einen Fehler. Nicht hinterlegte Pfade antworten mit 404. Gibt die Liste aller Aufrufe zurück. */
export function mockApi(routes: Record<string, RouteValue>): ApiCall[] {
  const calls: ApiCall[] = []
  for (const method of ['GET', 'POST', 'PATCH', 'PUT', 'DELETE'] as const) {
    vi.spyOn(apiClient, method).mockImplementation((async (path: string, init: ApiInit = {}) => {
      calls.push({ method, path, init })
      const key = `${method} ${path}`
      if (!(key in routes)) {
        return { error: { detail: `Kein Test-Mock für ${key}`, code: 'NOT_MOCKED' }, response: new Response(null, { status: 404 }) }
      }
      const route = routes[key]
      const value = typeof route === 'function' ? await (route as (init: ApiInit) => unknown)(init) : route
      if (value instanceof ApiFailure) {
        return { error: { detail: value.detail, code: value.code }, response: new Response(null, { status: value.status }) }
      }
      return { data: value, response: new Response(null, { status: 200 }) }
    }) as never)
  }
  return calls
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } },
  })
  const result = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
  return { ...result, queryClient }
}
