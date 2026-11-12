/** Einstellungen → „Verwaltungskonten“: Zugänge ohne Mitarbeiter, z. B. für die Steuerberatung. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders } from '../test/utils'
import { AdminAccountsPage } from './AdminAccountsPage'

const ROLES = [{ id: 4, name: 'Lohnbüro (nur lesen)', description: null, permissions: { PAYROLL: 'VIEW' }, account_count: 1 }]
const USERS = [
  { id: 1, email: 'admin@example.com', role: 'ADMIN', payroll_access: false, custom_role: null, two_factor_enabled: false },
  { id: 2, email: 'stb@example.com', role: 'HR', payroll_access: false, custom_role: { id: 4, name: 'Lohnbüro (nur lesen)' }, two_factor_enabled: false },
]

afterEach(() => vi.restoreAllMocks())

describe('Verwaltungskonten', () => {
  it('listet Konten mit eigener Rolle', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /hr-users': USERS, 'GET /roles': ROLES })
    renderWithProviders(<AdminAccountsPage />)
    expect(await screen.findByText('stb@example.com')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Eigene Rolle von stb@example.com')).toHaveValue('4'))
    // Admins bekommen keine eigene Rolle
    expect(screen.queryByLabelText('Eigene Rolle von admin@example.com')).not.toBeInTheDocument()
  })

  it('legt ein Konto für die Steuerberatung an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /hr-users': [], 'GET /roles': ROLES, 'POST /hr-users': USERS[1] })
    renderWithProviders(<AdminAccountsPage />)
    await userEvent.type(await screen.findByLabelText('E-Mail'), 'stb@example.com')
    await userEvent.type(screen.getByLabelText('Passwort'), 'geheim123')
    await waitFor(() => expect(screen.getByRole('option', { name: 'Lohnbüro (nur lesen)' })).toBeInTheDocument())
    await userEvent.selectOptions(screen.getByLabelText('Eigene Rolle'), '4')
    // Mit eigener Rolle entscheidet die Rolle über die Vergütung – der Haken entfällt
    expect(screen.queryByRole('checkbox', { name: /Vergütung/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Anlegen' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')).toBeDefined())
    expect(calls.find((c) => c.method === 'POST')!.init.body).toEqual({
      email: 'stb@example.com',
      password: 'geheim123',
      role: 'HR',
      payroll_access: false,
      two_factor_enabled: false,
      custom_role_id: 4,
    })
  })

  it('ändert die eigene Rolle und entfernt Zugänge', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const calls = mockApi({
      'GET /hr-users': USERS,
      'GET /roles': ROLES,
      'PATCH /hr-users/{hr_user_id}': USERS[1],
      'DELETE /hr-users/{hr_user_id}': null,
    })
    renderWithProviders(<AdminAccountsPage />)
    const select = await screen.findByLabelText('Eigene Rolle von stb@example.com')
    await userEvent.selectOptions(select, '')
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.init.body).toEqual({ custom_role_id: null }))
    await userEvent.click(screen.getAllByRole('button', { name: 'Zugang entfernen' })[1])
    await waitFor(() => expect(calls.find((c) => c.method === 'DELETE')?.init.params?.path).toEqual({ hr_user_id: 2 }))
  })

  it('zeigt Fehler des Servers', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /hr-users': [],
      'GET /roles': [],
      'POST /hr-users': new ApiFailure(409, 'EMAIL_TAKEN', 'Diese E-Mail wird bereits verwendet.'),
    })
    renderWithProviders(<AdminAccountsPage />)
    await userEvent.type(await screen.findByLabelText('E-Mail'), 'x@example.com')
    await userEvent.type(screen.getByLabelText('Passwort'), 'geheim123')
    await userEvent.click(screen.getByRole('button', { name: 'Anlegen' }))
    expect(await screen.findByText('Diese E-Mail wird bereits verwendet.')).toBeInTheDocument()
  })
})
