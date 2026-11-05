/** Zulagen & Einmalzahlungen unter „Vertrag & Vergütung“ (nur Admin). */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { EmploymentTab } from './EmploymentTab'

const allowance = {
  id: 1,
  employee_id: 7,
  kind: 'ALLOWANCE',
  name: 'Fahrtkosten',
  amount: 50,
  unit: 'PER_MONTH',
  valid_from: '2026-08-16',
  valid_to: null,
  pay_date: null,
  wage_type: '2000',
  note: null,
}

function lastBody(calls: ApiCall[], method: string) {
  return calls.filter((call) => call.method === method).at(-1)?.init.body as Record<string, unknown> | undefined
}

function routes() {
  return {
    'GET /employees/{employee_id}/contracts': [],
    'GET /employees/{employee_id}/compensation': [],
    'GET /employees/{employee_id}/pay-components': [allowance],
    'POST /employees/{employee_id}/pay-components': allowance,
    'PATCH /employees/{employee_id}/pay-components/{component_id}': { ...allowance, valid_to: '2026-12-31' },
  }
}

describe('Zulagen & Einmalzahlungen', () => {
  it('zeigt Zulagen und legt eine Einmalzahlung an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes())
    renderWithProviders(<EmploymentTab employeeId={7} isAdmin />)

    expect(await screen.findByText('Fahrtkosten')).toBeInTheDocument()
    expect(screen.getByText('50,00 EUR je Monat')).toBeInTheDocument()
    expect(screen.getByText('ab 16.8.2026, unbefristet')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Neue Einmalzahlung' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Bezeichnung')).toHaveValue('Weihnachtsgeld')
    await userEvent.type(within(dialog).getByLabelText('Betrag (EUR)'), '500,50')
    await userEvent.clear(within(dialog).getByLabelText('Auszahlung am'))
    await userEvent.type(within(dialog).getByLabelText('Auszahlung am'), '2026-11-30')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(lastBody(calls, 'POST')).toEqual({
        kind: 'ONE_TIME',
        name: 'Weihnachtsgeld',
        amount: 500.5,
        pay_date: '2026-11-30',
        wage_type: null,
        note: null,
      }),
    )
  })

  it('legt eine Zulage je Stunde an und beendet eine Zulage', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes())
    renderWithProviders(<EmploymentTab employeeId={7} isAdmin />)
    await screen.findByText('Fahrtkosten')

    await userEvent.click(screen.getByRole('button', { name: 'Neue Zulage' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Bezeichnung'), 'Erschwernis')
    await userEvent.click(within(dialog).getByRole('button', { name: /Je Stunde/ }))
    await userEvent.type(within(dialog).getByLabelText('Betrag je Stunde (EUR)'), '1,5')
    await userEvent.type(within(dialog).getByLabelText('Lohnart (optional)'), '2100')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(lastBody(calls, 'POST')).toMatchObject({ kind: 'ALLOWANCE', name: 'Erschwernis', amount: 1.5, unit: 'PER_HOUR', wage_type: '2100', valid_to: null }),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Beenden' }))
    const end = screen.getByLabelText('Gültig bis')
    await userEvent.clear(end)
    await userEvent.type(end, '2026-12-31')
    await userEvent.click(screen.getByRole('button', { name: 'OK' }))
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toEqual({ valid_to: '2026-12-31', clear_valid_to: false }))
  })

  it('ist für HR nicht sichtbar', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes())
    renderWithProviders(<EmploymentTab employeeId={7} isAdmin={false} />)
    await waitFor(() => expect(calls.some((call) => call.path.includes('contracts'))).toBe(true))
    expect(screen.queryByText('Zulagen & Einmalzahlungen')).not.toBeInTheDocument()
    expect(calls.some((call) => call.path.includes('pay-components'))).toBe(false)
  })
})
