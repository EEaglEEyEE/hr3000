/** Überstundenkonto: Auszahlung mit Faktor und „Neuen Kontostand festlegen“. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { BalanceAdjustmentsCard } from './BalanceAdjustmentsCard'

afterEach(() => vi.restoreAllMocks())

async function chooseAction(label: string) {
  await userEvent.click(screen.getAllByRole('combobox')[0])
  await userEvent.click(await screen.findByRole('option', { name: label }))
}

describe('Buchungen Überstundenkonto', () => {
  it('zahlt Überstunden mit Faktor aus', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/balance-adjustments': [],
      'POST /employees/{employee_id}/balance-adjustments': (init: ApiInit) => ({ id: 1, ...(init.body as object) }),
    })
    renderWithProviders(<BalanceAdjustmentsCard employeeId={5} canEdit />)
    await chooseAction('Überstunden auszahlen')
    await userEvent.type(screen.getByLabelText('Stunden'), '10')
    await userEvent.clear(screen.getByLabelText('Faktor'))
    await userEvent.type(screen.getByLabelText('Faktor'), '1,5')
    await userEvent.type(screen.getByLabelText('Begründung'), 'Auszahlung März')
    await userEvent.click(screen.getByRole('button', { name: 'Buchen' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.init.body).toMatchObject({ kind: 'PAYOUT', minutes: -600, payout_factor: 1.5 }),
    )
  })

  it('legt einen neuen Kontostand fest', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/balance-adjustments': [],
      'POST /employees/{employee_id}/balance-adjustments/set-balance': (init: ApiInit) => ({ id: 2, ...(init.body as object) }),
    })
    renderWithProviders(<BalanceAdjustmentsCard employeeId={5} canEdit />)
    await chooseAction('Neuen Kontostand festlegen')
    await userEvent.type(screen.getByLabelText('Neuer Kontostand (Stunden)'), '12,5')
    await userEvent.type(screen.getByLabelText('Begründung'), 'Stand Altsystem')
    await userEvent.click(screen.getByRole('button', { name: 'Buchen' }))
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('set-balance'))?.init.body).toMatchObject({ balance_minutes: 750 }),
    )
  })
})
