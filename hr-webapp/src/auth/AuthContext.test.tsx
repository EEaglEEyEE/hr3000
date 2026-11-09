/** Welche Rechte die Oberfläche aus dem Login-Token ableitet. Das Backend prüft dieselben Regeln
 * noch einmal – hier geht es darum, dass niemand Menüs/Knöpfe sieht, die er nicht nutzen darf. */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { fakeJwt, loginAs, renderWithProviders } from '../test/utils'
import { useAuth } from './AuthContext'

function Probe() {
  const auth = useAuth()
  return (
    <>
      <pre data-testid="auth">
        {JSON.stringify({
          isAuthenticated: auth.isAuthenticated,
          employeeId: auth.employeeId,
          hasHrAccess: auth.hasHrAccess,
          isAdmin: auth.isAdmin,
          isFullHr: auth.isFullHr,
          isSuperAdmin: auth.isSuperAdmin,
        })}
      </pre>
      <button type="button" onClick={auth.logout}>
        Abmelden
      </button>
    </>
  )
}

function auth() {
  return JSON.parse(screen.getByTestId('auth').textContent ?? '{}')
}

describe('Rechte aus dem Login', () => {
  it.each([
    { name: 'Verwaltungskonto Admin', login: { kind: 'hr', role: 'ADMIN' }, expected: { employeeId: null, hasHrAccess: true, isAdmin: true, isFullHr: true, isSuperAdmin: false } },
    { name: 'Verwaltungskonto HR', login: { kind: 'hr', role: 'HR' }, expected: { employeeId: null, hasHrAccess: true, isAdmin: false, isFullHr: true, isSuperAdmin: false } },
    { name: 'Verwaltungskonto Teamleader', login: { kind: 'hr', role: 'SUPERVISOR' }, expected: { employeeId: null, hasHrAccess: true, isAdmin: false, isFullHr: false, isSuperAdmin: false } },
    { name: 'Plattform-Admin', login: { kind: 'hr', role: 'SUPER_ADMIN' }, expected: { employeeId: null, hasHrAccess: true, isAdmin: false, isFullHr: true, isSuperAdmin: true } },
    { name: 'Mitarbeiter ohne Rolle', login: { kind: 'employee', employeeId: 7 }, expected: { employeeId: 7, hasHrAccess: false, isAdmin: false, isFullHr: false, isSuperAdmin: false } },
    { name: 'Mitarbeiter mit Admin-Rolle', login: { kind: 'employee', employeeId: 7, hrRole: 'ADMIN' }, expected: { employeeId: 7, hasHrAccess: true, isAdmin: true, isFullHr: true, isSuperAdmin: false } },
    { name: 'Mitarbeiter als Teamleader', login: { kind: 'employee', employeeId: 7, hrRole: 'SUPERVISOR' }, expected: { employeeId: 7, hasHrAccess: true, isAdmin: false, isFullHr: false, isSuperAdmin: false } },
  ] as const)('$name', ({ login, expected }) => {
    loginAs(login)
    renderWithProviders(<Probe />)
    expect(auth()).toMatchObject({ isAuthenticated: true, ...expected })
  })

  it('ohne Anmeldung gibt es keinerlei Rechte', () => {
    renderWithProviders(<Probe />)
    expect(auth()).toEqual({
      isAuthenticated: false,
      employeeId: null,
      hasHrAccess: false,
      isAdmin: false,
      isFullHr: false,
      isSuperAdmin: false,
    })
  })

  it('ein kaputtes Token führt nicht zum Absturz und gibt keine Rechte', () => {
    localStorage.setItem('hr3000.access_token', 'kein.gueltiges%%%.token')
    localStorage.setItem('hr3000.refresh_token', 'x')
    renderWithProviders(<Probe />)
    expect(auth()).toMatchObject({ isAdmin: false, isFullHr: false, isSuperAdmin: false })
  })

  it('eine unbekannte Rolle im Token gibt keine Admin-/HR-Rechte', () => {
    const token = fakeJwt({ sub: '1', type: 'account_access', role: 'ROOT', emp: null })
    localStorage.setItem('hr3000.access_token', token)
    localStorage.setItem('hr3000.refresh_token', token)
    renderWithProviders(<Probe />)
    expect(auth()).toMatchObject({ hasHrAccess: false, isAdmin: false, isFullHr: false, isSuperAdmin: false })
  })

  it('Abmelden entfernt Rechte und gespeicherte Tokens', async () => {
    loginAs({ kind: 'employee', employeeId: 7, hrRole: 'ADMIN' })
    renderWithProviders(<Probe />)
    await userEvent.click(screen.getByRole('button', { name: 'Abmelden' }))
    expect(auth()).toMatchObject({ isAuthenticated: false, employeeId: null, hasHrAccess: false, isAdmin: false })
    expect(localStorage.getItem('hr3000.access_token')).toBeNull()
    expect(localStorage.getItem('hr3000.refresh_token')).toBeNull()
  })
})
