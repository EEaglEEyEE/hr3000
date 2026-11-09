/** Urlaubsanspruch: berechnet aus dem Jahresurlaub (Vertrag bzw. Standard) oder je Jahr fest eingetragen. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { LeaveEntitlement } from '../../api/queries/leaveEntitlements'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { LeaveEntitlementCard } from './LeaveEntitlementCard'

function entitlement(overrides: Partial<LeaveEntitlement> = {}): LeaveEntitlement {
  return {
    employee_id: 7,
    year: new Date().getFullYear(),
    entitled_days: 24,
    carried_over_days: 0,
    used_days: 4,
    remaining_days: 20,
    carried_over_auto: false,
    expired_days: 0,
    expiring_days: 0,
    expiry_date: null,
    suggested_entitled_days: 24,
    entitled_manual: false,
    annual_vacation_days: 30,
    workdays_per_week: 4,
    adjustment_days: 0,
    ...overrides,
  }
}

function patchBodies(calls: ApiCall[]) {
  return calls.filter((call) => call.method === 'PATCH').map((call) => call.init.body)
}

describe('Urlaubsanspruch', () => {
  it('zeigt den berechneten Anspruch und schreibt ihn beim Ändern nur des Übertrags nicht fest', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /employees/{employee_id}/leave-entitlement': entitlement(),
      'GET /employees/{employee_id}/leave-adjustments': [],
      'PATCH /employees/{employee_id}/leave-entitlement': (init: ApiInit) => entitlement(init.body as object),
    })
    renderWithProviders(<LeaveEntitlementCard employeeId={7} />)
    expect(await screen.findByText('Anspruch (berechnet)')).toBeInTheDocument()
    expect(screen.getByText(/Berechnet aus 30 Tagen Jahresurlaub/)).toBeInTheDocument()
    expect(screen.queryByText(/Berechnet wären/)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Bearbeiten' }))
    const carried = screen.getByLabelText('Übertrag Vorjahr (Tage)')
    await userEvent.clear(carried)
    await userEvent.type(carried, '3')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(patchBodies(calls)).toEqual([{ carried_over_days: 3 }]))
  })

  it('zeigt einen fest eingetragenen Anspruch und kann wieder berechnen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /employees/{employee_id}/leave-entitlement': entitlement({ entitled_days: 26, entitled_manual: true, remaining_days: 22 }),
      'GET /employees/{employee_id}/leave-adjustments': [],
      'PATCH /employees/{employee_id}/leave-entitlement': () => entitlement(),
    })
    renderWithProviders(<LeaveEntitlementCard employeeId={7} />)
    expect(await screen.findByText('Anspruch (fest eingetragen)')).toBeInTheDocument()
    expect(screen.getByText(/Berechnet wären 24 Tage/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Wieder berechnen' }))
    await waitFor(() => expect(patchBodies(calls)).toEqual([{ entitled_auto: true }]))
  })

  it('verlangt bei „Nach Aufwand“ einen eingetragenen Anspruch', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /employees/{employee_id}/leave-entitlement': entitlement({ suggested_entitled_days: null, entitled_days: 0, workdays_per_week: null }),
    })
    renderWithProviders(<LeaveEntitlementCard employeeId={7} />)
    expect(await screen.findByText(/Anspruch bitte eintragen/)).toBeInTheDocument()
  })
})
