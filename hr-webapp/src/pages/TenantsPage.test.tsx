/** Super-Admin: Mandantenliste kennzeichnet selbst registrierte Firmen (hr3000.de/registrieren). */
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { TenantsPage } from './TenantsPage'

function tenant(overrides: Record<string, unknown>) {
  return {
    id: 1,
    subdomain: 'lassner',
    name: 'Lassner KG',
    status: 'ACTIVE',
    plan: 'UNLIMITED',
    contact_email: null,
    contact_name: null,
    active_employees: 12,
    self_signup: false,
    created_at: '2026-10-12T10:00:00',
    ...overrides,
  }
}

describe('Mandantenliste', () => {
  it('zeigt Selbstregistrierungen mit Datum und Ansprechpartner', async () => {
    loginAs({ kind: 'hr', role: 'SUPER_ADMIN' })
    mockApi({
      'GET /tenants': [
        tenant({}),
        tenant({
          id: 2,
          subdomain: 'neue-firma',
          name: 'Neue Firma GmbH',
          plan: 'FREE',
          active_employees: 0,
          self_signup: true,
          contact_name: 'Nina Neu',
          created_at: '2026-11-04T09:30:00',
        }),
      ],
    })
    renderWithProviders(<TenantsPage />)
    expect(await screen.findByText('Neue Firma GmbH')).toBeInTheDocument()
    expect(screen.getByText(/Selbst registriert am 4\.11\.2026/)).toHaveTextContent('Nina Neu')
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument()
    // Vom Super-Admin angelegte Firmen ohne Kennzeichnung.
    expect(screen.getAllByText(/Selbst registriert/)).toHaveLength(1)
  })
})

describe('Mandantenliste: Kündigen und Löschen', () => {
  it('kündigt, zeigt den Löschtermin und löscht nur mit eingetippter Subdomain', async () => {
    const { default: userEvent } = await import('@testing-library/user-event')
    const { waitFor } = await import('@testing-library/react')
    loginAs({ kind: 'hr', role: 'SUPER_ADMIN' })
    const calls = mockApi({
      'GET /tenants': [
        tenant({ id: 3, subdomain: 'spam', name: 'Spam GmbH', plan: 'FREE', active_employees: 0 }),
        tenant({ id: 4, subdomain: 'weg', name: 'Weg GmbH', plan: 'FREE', active_employees: 0, deletion_due_on: '2026-12-30' }),
      ],
      'POST /tenants/{tenant_id}/cancel': tenant({ id: 3 }),
      'POST /tenants/{tenant_id}/cancel/revoke': tenant({ id: 4 }),
      'POST /tenants/{tenant_id}/purge': { subdomain: 'spam', deleted_rows: 12 },
    })
    renderWithProviders(<TenantsPage />)
    expect(await screen.findByText('Gekündigt – Löschung am 30.12.2026')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Kündigen' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/tenants/{tenant_id}/cancel')).toBe(true))
    await userEvent.click(screen.getByRole('button', { name: 'Kündigung zurücknehmen' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/tenants/{tenant_id}/cancel/revoke')).toBe(true))

    await userEvent.click(screen.getAllByRole('button', { name: 'Endgültig löschen…' })[0])
    const purge = screen.getByRole('button', { name: 'Endgültig löschen' })
    expect(purge).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Subdomain eingeben/), 'spam')
    await userEvent.click(purge)
    await waitFor(() => {
      const call = calls.find((c) => c.path === '/tenants/{tenant_id}/purge')
      expect(call?.init.body).toEqual({ confirm_subdomain: 'spam' })
      expect(call?.init.params?.path).toEqual({ tenant_id: 3 })
    })
  })
})
