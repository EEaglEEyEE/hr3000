/** Datenänderungen: Vorschlag aus „Meine Daten“ und Entscheidung unter „Zu klären“. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { PendingChangeRequests, ProposeChange } from './ChangeRequests'

const request = {
  id: 4, employee_id: 7, employee_name: 'Erika Muster', status: 'PENDING', created_at: '2026-11-07T10:00:00',
  decided_at: null, decision_note: null, note: 'Umgezogen', contains_payroll: true,
  items: [{ field: 'city', label: 'Ort', old: 'Fulda', new: 'Kassel' }, { field: 'iban', label: 'IBAN', old: null, new: '•••' }],
}

describe('Datenänderungen', () => {
  it('schickt nur geänderte Felder', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    const calls = mockApi({
      'GET /me/change-requests': [],
      'GET /me/personal-data': { city: 'Fulda', payroll_visible: true },
      'GET /me/attributes': [],
      'GET /me/attribute-values': [],
      'POST /me/change-requests': { ...request, items: [] },
    })
    renderWithProviders(<ProposeChange />)
    await userEvent.click(screen.getByRole('button', { name: 'Änderung vorschlagen' }))
    const city = await screen.findByLabelText('Ort')
    await waitFor(() => expect(city).toHaveValue('Fulda'))
    await userEvent.clear(city)
    await userEvent.type(city, 'Kassel')
    await userEvent.click(screen.getByRole('button', { name: 'Vorschlag senden' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.init.body).toEqual({ personal: { city: 'Kassel' }, attributes: {}, note: null }),
    )
  })

  it('ohne Lohn-Freigabe kein Übernehmen bei Bankdaten', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /change-requests': [request] })
    renderWithProviders(<PendingChangeRequests />)
    expect(await screen.findByText('Kassel')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Übernehmen' })).not.toBeInTheDocument()
  })

  it('übernimmt mit Freigabe', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /change-requests': [request],
      'POST /change-requests/{request_id}/decide': { ...request, status: 'APPROVED' },
    })
    renderWithProviders(<PendingChangeRequests />)
    await userEvent.click(await screen.findByRole('button', { name: 'Übernehmen' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.init.body).toEqual({ approve: true, note: null }))
  })
})
