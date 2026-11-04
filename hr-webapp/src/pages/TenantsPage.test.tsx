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
