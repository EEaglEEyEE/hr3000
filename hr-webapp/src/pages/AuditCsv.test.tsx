/** Audit-Protokoll: Anmeldungen erscheinen, „CSV exportieren“ lädt die angezeigten Einträge. */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as csv from '../lib/csv'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { AuditLogPage } from './AuditLogPage'

afterEach(() => vi.restoreAllMocks())

describe('Audit-Protokoll', () => {
  it('zeigt Anmeldungen und exportiert sie als CSV', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /audit-log': [
        { id: 1, actor_label: 'Erika Muster', action: 'LOGIN', entity_type: 'employee', entity_id: 5, detail: 'Anmeldung', created_at: '2026-11-07T08:00:00' },
      ],
    })
    const spy = vi.spyOn(csv, 'downloadCsv').mockImplementation(() => {})
    renderWithProviders(<AuditLogPage />)
    expect(await screen.findByText('Erika Muster')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /CSV exportieren/ }))
    expect(spy).toHaveBeenCalledTimes(1)
    const [, header, rows] = spy.mock.calls[0]
    expect(header).toEqual(['Zeitpunkt', 'Person', 'Aktion', 'Bereich', 'ID', 'Detail'])
    expect(rows[0].slice(1)).toEqual(['Erika Muster', 'Anmeldung', 'Mitarbeiter', 5, 'Anmeldung'])
  })
})
