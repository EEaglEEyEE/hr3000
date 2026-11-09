/** „HR-Berechtigung“: Admins geben HR-Personen die Berechtigung „Vergütung & Lohn-Export“. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { EmployeeForm } from './EmployeeFormDialog'

const LOCATIONS = [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }] as never

const employee = {
  id: 7, location_id: 1, first_name: 'Hanna', last_name: 'Personal', employee_number: '1003', active: true,
  login_email: 'hanna@example.com', hr_role: 'HR', hr_payroll_access: false, auto_break_enabled: true, has_pin: false,
  nfc_uid: null, hire_date: null, termination_date: null, birth_date: null, show_birthday_in_calendar: true, team_id: null,
  anonymized_at: null,
} as never

describe('HR-Berechtigung: Vergütung & Lohn-Export', () => {
  it('schaltet die Berechtigung für HR an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true },
      'GET /teams': [],
      'PATCH /employees/{employee_id}/hr-role': (init: ApiInit) => ({ ...(employee as object), hr_payroll_access: (init.body as { payroll_access?: boolean }).payroll_access }),
    })
    renderWithProviders(<EmployeeForm employee={employee} locations={LOCATIONS} />)
    const box = await screen.findByRole('checkbox', { name: /Vergütung & Lohn-Export/ })
    expect(box).not.toBeChecked()
    await userEvent.click(box)
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.init.body).toEqual({ hr_role: 'HR', payroll_access: true }),
    )
    expect(box).toBeChecked()
  })

  it('zeigt die Freigabe nur bei HR', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /features': {}, 'GET /teams': [] })
    renderWithProviders(
      <EmployeeForm employee={{ ...(employee as object), hr_role: 'SUPERVISOR' } as never} locations={LOCATIONS} />,
    )
    await screen.findByText('HR-Berechtigung')
    expect(screen.queryByRole('checkbox', { name: /Vergütung & Lohn-Export/ })).not.toBeInTheDocument()
  })
})
