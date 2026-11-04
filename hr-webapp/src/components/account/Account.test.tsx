/** Konto: Passwort ändern, Kündigung (Einstellungen + Hinweis), Login mit "Passwort vergessen",
 * Seite "Neues Passwort". */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from '../../pages/LoginPage'
import { ResetPasswordPage } from '../../pages/ResetPasswordPage'
import { ApiFailure, fakeJwt, loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { AccountCancellationCard, CancellationBanner } from './AccountCancellation'
import { ChangePasswordButton } from './ChangePasswordDialog'

function plan(overrides: Record<string, unknown> = {}) {
  return {
    plan: 'FREE', active_employees: 3, limit: 5, remaining: 2,
    cancelled_at: null, contract_end: null, deletion_due_on: null, ...overrides,
  }
}

function bodyOf(calls: ApiCall[], path: string) {
  return calls.filter((c) => c.path === path).at(-1)?.init.body as Record<string, unknown> | undefined
}

/** fetch-Attrappe für Seiten, die ohne apiClient arbeiten (Login, Branding). */
function mockFetch(routes: Record<string, (body: unknown) => { status: number; json?: unknown }>) {
  const calls: { url: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ url, body })
    const route = routes[url]
    const result = route ? route(body) : { status: 404, json: { detail: 'nicht gemockt' } }
    return new Response(result.json === undefined ? null : JSON.stringify(result.json), { status: result.status })
  })
  return calls
}

afterEach(() => {
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

describe('Passwort ändern', () => {
  it('prüft die Eingaben, ändert das Passwort und übernimmt die neuen Tokens', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const newAccess = fakeJwt({ sub: '1', role: 'ADMIN', type: 'hr', neu: true })
    const calls = mockApi({ 'POST /auth/change-password': { access_token: newAccess, refresh_token: 'r-neu', token_type: 'bearer' } })
    renderWithProviders(<ChangePasswordButton />)
    await userEvent.click(screen.getByRole('button', { name: /Passwort ändern/ }))
    await userEvent.type(screen.getByLabelText('Aktuelles Passwort'), 'altes-passwort')
    await userEvent.type(screen.getByLabelText('Neues Passwort'), 'kurz')
    await userEvent.type(screen.getByLabelText('Neues Passwort wiederholen'), 'kurz')
    await userEvent.click(screen.getByRole('button', { name: 'Passwort ändern' }))
    expect(screen.getByRole('alert')).toHaveTextContent('mindestens 10 Zeichen')
    expect(calls).toHaveLength(0)

    await userEvent.clear(screen.getByLabelText('Neues Passwort'))
    await userEvent.type(screen.getByLabelText('Neues Passwort'), 'neues-passwort-1')
    await userEvent.clear(screen.getByLabelText('Neues Passwort wiederholen'))
    await userEvent.type(screen.getByLabelText('Neues Passwort wiederholen'), 'anderes-passwort')
    await userEvent.click(screen.getByRole('button', { name: 'Passwort ändern' }))
    expect(screen.getByRole('alert')).toHaveTextContent('stimmen nicht überein')

    await userEvent.clear(screen.getByLabelText('Neues Passwort wiederholen'))
    await userEvent.type(screen.getByLabelText('Neues Passwort wiederholen'), 'neues-passwort-1')
    await userEvent.click(screen.getByRole('button', { name: 'Passwort ändern' }))
    expect(await screen.findByText(/Dein Passwort ist geändert/)).toBeInTheDocument()
    expect(bodyOf(calls, '/auth/change-password')).toEqual({ current_password: 'altes-passwort', new_password: 'neues-passwort-1' })
    expect(localStorage.getItem('hr3000.access_token')).toBe(newAccess)
    expect(localStorage.getItem('hr3000.refresh_token')).toBe('r-neu')
  })

  it('zeigt einen falschen aktuellen Wert als Fehler', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    mockApi({ 'POST /auth/change-password': new ApiFailure(400, 'PASSWORD_WRONG', 'Das aktuelle Passwort stimmt nicht.') })
    renderWithProviders(<ChangePasswordButton />)
    await userEvent.click(screen.getByRole('button', { name: /Passwort ändern/ }))
    await userEvent.type(screen.getByLabelText('Aktuelles Passwort'), 'falsch')
    await userEvent.type(screen.getByLabelText('Neues Passwort'), 'neues-passwort-1')
    await userEvent.type(screen.getByLabelText('Neues Passwort wiederholen'), 'neues-passwort-1')
    await userEvent.click(screen.getByRole('button', { name: 'Passwort ändern' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Das aktuelle Passwort stimmt nicht.')
  })
})

describe('Kündigung', () => {
  it('kündigt nur mit eingetippter Adresse der Firma', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /plan': plan(), 'POST /account/cancel': plan({ contract_end: '2026-11-30', deletion_due_on: '2026-12-30' }) })
    renderWithProviders(<AccountCancellationCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'HR3000 kündigen…' }))
    const confirm = screen.getByRole('button', { name: 'Verbindlich kündigen' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Adresse eurer Firma eingeben/), 'falsch')
    expect(confirm).toBeDisabled()
    await userEvent.clear(screen.getByLabelText(/Adresse eurer Firma eingeben/))
    await userEvent.type(screen.getByLabelText(/Adresse eurer Firma eingeben/), window.location.hostname.split('.')[0])
    await userEvent.click(confirm)
    await waitFor(() => expect(bodyOf(calls, '/account/cancel')).toEqual({ confirm_subdomain: window.location.hostname.split('.')[0] }))
  })

  it('zeigt Termine einer laufenden Kündigung und nimmt sie zurück', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /plan': plan({ cancelled_at: '2026-11-04T10:00:00', contract_end: '2026-11-30', deletion_due_on: '2026-12-30' }),
      'POST /account/cancel/revoke': plan(),
    })
    renderWithProviders(<AccountCancellationCard />)
    expect(await screen.findByText(/Gekündigt zum 30\.11\.2026/)).toHaveTextContent('30.12.2026')
    await userEvent.click(screen.getByRole('button', { name: 'Kündigung zurücknehmen' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/account/cancel/revoke')).toBe(true))
  })

  it('Hinweis in der HR-Ansicht nur bei laufender Kündigung', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /plan': plan({ deletion_due_on: '2026-12-30' }) })
    const { unmount } = renderWithProviders(<CancellationBanner />)
    expect(await screen.findByRole('status')).toHaveTextContent('30.12.2026')
    expect(screen.queryByText(/Zurücknehmen unter/)).not.toBeInTheDocument() // nur für Admins
    unmount()
    vi.restoreAllMocks()
    mockApi({ 'GET /plan': plan() })
    const { container } = renderWithProviders(<CancellationBanner />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})

describe('Anmeldung', () => {
  it('bietet "Passwort vergessen" an, wenn Mailversand eingerichtet ist', async () => {
    const calls = mockFetch({
      '/api/branding': () => ({ status: 200, json: { tenant_name: 'Musterfirma', logo_data_url: null, password_reset_available: true } }),
      '/api/auth/password-reset/request': () => ({ status: 202, json: { detail: 'Wenn es ein Konto gibt, haben wir dir einen Link geschickt.' } }),
    })
    renderWithProviders(<LoginPage />, { route: '/login' })
    await userEvent.click(await screen.findByRole('button', { name: 'Passwort vergessen?' }))
    await userEvent.type(screen.getByLabelText('E-Mail'), 'erika@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Link schicken' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Bitte prüf dein Postfach')
    expect(calls.find((c) => c.url === '/api/auth/password-reset/request')?.body).toEqual({ email: 'erika@example.com' })
  })

  it('verweist ohne Mailversand an die Personalabteilung', async () => {
    mockFetch({ '/api/branding': () => ({ status: 200, json: { tenant_name: 'Musterfirma', logo_data_url: null, password_reset_available: false } }) })
    renderWithProviders(<LoginPage />, { route: '/login' })
    expect(await screen.findByText(/wende dich an deine Personalabteilung/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Passwort vergessen?' })).not.toBeInTheDocument()
  })

  it('erklärt eine noch nicht bestätigte E-Mail-Adresse statt "Passwort falsch"', async () => {
    const calls = mockFetch({
      '/api/branding': () => ({ status: 200, json: { tenant_name: null, logo_data_url: null } }),
      '/api/auth/hr/login': () => ({ status: 403, json: { detail: 'Bitte bestätige zuerst deine E-Mail-Adresse.', code: 'EMAIL_NOT_VERIFIED' } }),
    })
    renderWithProviders(<LoginPage />, { route: '/login' })
    await userEvent.type(screen.getByLabelText('E-Mail'), 'nina@example.com')
    await userEvent.type(screen.getByLabelText('Passwort'), 'sehr-geheim-123')
    await userEvent.click(screen.getByRole('button', { name: 'Anmelden' }))
    expect(await screen.findByText('Bitte bestätige zuerst deine E-Mail-Adresse.')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/api/auth/employee/login')).toBe(false)
  })
})

describe('Neues Passwort (Link aus der E-Mail)', () => {
  it('setzt das Passwort mit dem Token aus dem Link und entfernt es aus der Adresszeile', async () => {
    window.history.replaceState(null, '', '/passwort-zuruecksetzen#token=abcdefghijklmnopqrstuvwxyz012345')
    const calls = mockFetch({ '/api/auth/password-reset/confirm': () => ({ status: 204 }) })
    renderWithProviders(<ResetPasswordPage />)
    expect(window.location.hash).toBe('')
    await userEvent.type(screen.getByLabelText('Neues Passwort'), 'neues-passwort-1')
    await userEvent.type(screen.getByLabelText('Neues Passwort wiederholen'), 'neues-passwort-1')
    await userEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }))
    expect(await screen.findByRole('status')).toHaveTextContent('gespeichert')
    expect(calls.find((c) => c.url === '/api/auth/password-reset/confirm')?.body).toEqual({
      token: 'abcdefghijklmnopqrstuvwxyz012345',
      new_password: 'neues-passwort-1',
    })
  })

  it('meldet einen abgelaufenen Link', async () => {
    window.history.replaceState(null, '', '/passwort-zuruecksetzen#token=abcdefghijklmnopqrstuvwxyz012345')
    mockFetch({ '/api/auth/password-reset/confirm': () => ({ status: 400, json: { detail: 'Der Link ist ungültig oder abgelaufen.', code: 'TOKEN_INVALID' } }) })
    renderWithProviders(<ResetPasswordPage />)
    await userEvent.type(screen.getByLabelText('Neues Passwort'), 'neues-passwort-1')
    await userEvent.type(screen.getByLabelText('Neues Passwort wiederholen'), 'neues-passwort-1')
    await userEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('ungültig oder abgelaufen')
  })

  it('ohne Token im Link nur ein Hinweis', () => {
    window.history.replaceState(null, '', '/passwort-zuruecksetzen')
    renderWithProviders(<ResetPasswordPage />)
    expect(screen.getByText(/Link ist unvollständig/)).toBeInTheDocument()
  })
})
