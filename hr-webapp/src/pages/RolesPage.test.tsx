/** Einstellungen → „Rollen“: eigene Rollen mit Matrix Bereich × Stufe. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders } from '../test/utils'
import { RolesPage } from './RolesPage'

const META = {
  areas: [
    { key: 'EMPLOYEES', label: 'Mitarbeiter & Stammdaten', description: 'Liste' },
    { key: 'PAYROLL', label: 'Vergütung & Lohn', description: 'Lohn' },
    { key: 'TIME', label: 'Zeiterfassung & „Zu klären“', description: 'Zeiten' },
  ],
  templates: [
    {
      key: 'PAYROLL_OFFICE_READONLY',
      name: 'Lohnbüro (nur lesen)',
      description: 'Steuerberatung',
      permissions: { EMPLOYEES: 'NONE', PAYROLL: 'VIEW', TIME: 'NONE' },
    },
  ],
}

const ROLE = {
  id: 3,
  name: 'Zeiten',
  description: 'Nur Zeiterfassung',
  permissions: { EMPLOYEES: 'NONE', PAYROLL: 'NONE', TIME: 'EDIT' },
  account_count: 0,
}

afterEach(() => vi.restoreAllMocks())

describe('Rollen', () => {
  it('listet Rollen mit Kurzfassung der Rechte', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /roles': [{ ...ROLE, account_count: 2 }], 'GET /roles/meta': META })
    renderWithProviders(<RolesPage />)
    expect(await screen.findByText('Zeiten')).toBeInTheDocument()
    expect(screen.getByText('2 Konten')).toBeInTheDocument()
    expect(await screen.findByText('Zeiterfassung & „Zu klären“: bearbeiten')).toBeInTheDocument()
    // Zugewiesene Rollen lassen sich nicht löschen
    expect(screen.getByRole('button', { name: 'Löschen' })).toBeDisabled()
  })

  it('legt aus der Vorlage „Lohnbüro (nur lesen)“ an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /roles': [],
      'GET /roles/meta': META,
      'POST /roles': { ...ROLE, id: 9, name: 'Lohnbüro (nur lesen)' },
    })
    renderWithProviders(<RolesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Vorlage „Lohnbüro \(nur lesen\)“/ }))
    expect(screen.getByLabelText('Name')).toHaveValue('Lohnbüro (nur lesen)')
    expect(screen.getByRole('radio', { name: 'Vergütung & Lohn: Ansehen' })).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')).toBeDefined())
    const body = calls.find((c) => c.method === 'POST')!.init.body as { name: string; permissions: Record<string, string> }
    expect(body.name).toBe('Lohnbüro (nur lesen)')
    expect(body.permissions.PAYROLL).toBe('VIEW')
    expect(body.permissions.EMPLOYEES).toBe('NONE')
  })

  it('verlangt mindestens einen Bereich', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /roles': [], 'GET /roles/meta': META })
    renderWithProviders(<RolesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Neue Rolle' }))
    await userEvent.type(screen.getByLabelText('Name'), 'Leer')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/Mindestens ein Bereich/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('bearbeitet eine Rolle über die Matrix', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /roles': [ROLE], 'GET /roles/meta': META, 'PATCH /roles/{role_id}': ROLE })
    renderWithProviders(<RolesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await userEvent.click(screen.getByRole('radio', { name: 'Mitarbeiter & Stammdaten: Ansehen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')).toBeDefined())
    const patch = calls.find((c) => c.method === 'PATCH')!
    expect(patch.init.params?.path).toEqual({ role_id: 3 })
    expect((patch.init.body as { permissions: Record<string, string> }).permissions).toMatchObject({ EMPLOYEES: 'VIEW', TIME: 'EDIT' })
  })

  it('zeigt Konflikte des Servers an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockApi({
      'GET /roles': [ROLE],
      'GET /roles/meta': META,
      'DELETE /roles/{role_id}': new ApiFailure(409, 'ROLE_IN_USE', 'Die Rolle ist noch 1 Konto/Konten zugewiesen.'),
    })
    renderWithProviders(<RolesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Löschen' }))
    expect(await screen.findByText(/noch 1 Konto/)).toBeInTheDocument()
  })
})
