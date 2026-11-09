/** Zwei-Faktor-Anmeldung in der Webapp: Code-Schritt beim Login, Pflicht-Einrichtung beim Login und
 * Einrichten im Konto-Dialog (neue Tokens, Wiederherstellungscodes). */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from '../../pages/LoginPage'
import { fakeJwt, loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { TwoFactorButton } from './TwoFactorDialog'

const SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
const ACCESS = fakeJwt({ sub: '1', type: 'account_access', role: 'ADMIN', emp: null })

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

const branding = () => ({ status: 200, json: { tenant_name: null, logo_data_url: null } })

async function signIn() {
  renderWithProviders(<LoginPage />, { route: '/login' })
  await userEvent.type(screen.getByLabelText('E-Mail'), 'chefin@example.com')
  await userEvent.type(screen.getByLabelText('Passwort'), 'sehr-geheim-123')
  await userEvent.click(screen.getByRole('button', { name: 'Anmelden' }))
}

afterEach(() => vi.restoreAllMocks())

describe('Anmeldung mit Zwei-Faktor', () => {
  it('fragt nach dem Code und meldet erst danach an', async () => {
    const calls = mockFetch({
      '/api/branding': branding,
      '/api/auth/login': () => ({ status: 200, json: { two_factor: 'required', challenge_token: 'ch-1', access_token: null, refresh_token: null } }),
      '/api/auth/login/2fa': (body) =>
        (body as { code: string }).code === '123456'
          ? { status: 200, json: { access_token: ACCESS, refresh_token: 'r', token_type: 'bearer' } }
          : { status: 400, json: { detail: 'Der Code stimmt nicht.', code: 'TWO_FACTOR_CODE_INVALID' } },
    })
    await signIn()
    expect(await screen.findByText('Bestätigungscode')).toBeInTheDocument()
    expect(localStorage.getItem('hr3000.access_token')).toBeNull()

    await userEvent.type(screen.getByLabelText('Code'), '000000')
    await userEvent.click(screen.getByRole('button', { name: 'Anmelden' }))
    expect(await screen.findByText('Der Code stimmt nicht.')).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Code'))
    await userEvent.type(screen.getByLabelText('Code'), '123456')
    await userEvent.click(screen.getByRole('button', { name: 'Anmelden' }))
    await waitFor(() => expect(localStorage.getItem('hr3000.access_token')).toBe(ACCESS))
    expect(calls.filter((c) => c.url === '/api/auth/login/2fa').at(-1)?.body).toEqual({ challenge_token: 'ch-1', code: '123456' })
  })

  it('richtet die Pflicht-Zwei-Faktor-Anmeldung direkt beim Login ein', async () => {
    const calls = mockFetch({
      '/api/branding': branding,
      '/api/auth/login': () => ({ status: 200, json: { two_factor: 'setup', challenge_token: 'ch-setup', access_token: null, refresh_token: null } }),
      '/api/auth/2fa/setup': () => ({ status: 200, json: { secret: SECRET, otpauth_uri: `otpauth://totp/HR3000:x?secret=${SECRET}` } }),
      '/api/auth/2fa/enable': () => ({
        status: 200,
        json: { recovery_codes: ['abcd-efgh', 'ijkm-npqr'], access_token: ACCESS, refresh_token: 'r' },
      }),
    })
    await signIn()
    expect(await screen.findByText('Zwei-Faktor-Anmeldung einrichten')).toBeInTheDocument()
    expect(await screen.findByTestId('totp-secret')).toHaveTextContent('JBSW Y3DP')
    await userEvent.type(screen.getByLabelText('Code aus der App'), '654321')
    await userEvent.click(screen.getByRole('button', { name: 'Aktivieren' }))
    expect(await screen.findByText('abcd-efgh')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Codes gesichert – weiter' }))
    await waitFor(() => expect(localStorage.getItem('hr3000.access_token')).toBe(ACCESS))
    expect(calls.filter((c) => c.url === '/api/auth/2fa/setup')).toHaveLength(1)
    expect(calls.find((c) => c.url === '/api/auth/2fa/enable')?.body).toEqual({ challenge_token: 'ch-setup', code: '654321' })
  })
})

describe('Zwei-Faktor im Konto-Dialog', () => {
  it('richtet sie ein und übernimmt die neuen Tokens', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const newAccess = fakeJwt({ sub: '1', type: 'account_access', role: 'HR', emp: null, neu: true })
    const calls = mockApi({
      'GET /auth/2fa': { enabled: false, required: false, recovery_codes_left: 0 },
      'POST /auth/2fa/setup': { secret: SECRET, otpauth_uri: `otpauth://totp/HR3000:x?secret=${SECRET}` },
      'POST /auth/2fa/enable': { recovery_codes: ['abcd-efgh'], access_token: newAccess, refresh_token: 'r-neu' },
    })
    renderWithProviders(<TwoFactorButton />)
    await userEvent.click(screen.getByRole('button', { name: /Zwei-Faktor-Anmeldung/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Einrichten' }))
    await userEvent.type(await screen.findByLabelText('Code aus der App'), '111222')
    await userEvent.click(screen.getByRole('button', { name: 'Aktivieren' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Codes gesichert – weiter' }))
    expect(localStorage.getItem('hr3000.access_token')).toBe(newAccess)
    expect(calls.find((c) => c.path === '/auth/2fa/enable')?.init.body).toEqual({ code: '111222' })
  })

  it('zeigt bei Pflicht kein Abschalten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /auth/2fa': { enabled: true, required: true, recovery_codes_left: 7 } })
    renderWithProviders(<TwoFactorButton />)
    await userEvent.click(screen.getByRole('button', { name: /Zwei-Faktor-Anmeldung/ }))
    expect(await screen.findByText(/Noch 7 Wiederherstellungscodes/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Abschalten/ })).not.toBeInTheDocument()
  })
})
