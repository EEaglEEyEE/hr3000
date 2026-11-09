/** API & Webhooks: Secrets nur einmal anzeigen. */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { IntegrationsPage } from './IntegrationsPage'

describe('API & Webhooks', () => {
  it('zeigt Client-ID und Secret nach dem Anlegen einmal an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /api-clients': [],
      'GET /webhooks': [],
      'POST /api-clients': {
        id: 1, name: 'Lohn', client_id: 'hr3000_abc', client_secret: 's3cr3t', scopes: ['employees:read'],
        created_at: '2026-11-07T10:00:00', last_used_at: null, revoked_at: null,
      },
    })
    renderWithProviders(<IntegrationsPage />)
    await userEvent.type(screen.getByLabelText('Name'), 'Lohn')
    await userEvent.click(screen.getByRole('button', { name: 'Zugang anlegen' }))
    expect(await screen.findByTestId('secret')).toHaveTextContent('s3cr3t')
    expect(calls.find((c) => c.method === 'POST')?.init.body).toEqual({ name: 'Lohn', scopes: ['employees:read'] })
    await userEvent.click(screen.getByRole('button', { name: 'Gesichert – ausblenden' }))
    expect(screen.queryByTestId('secret')).not.toBeInTheDocument()
  })
})
