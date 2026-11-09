/** Mitarbeiter bearbeiten im Reiter „Einstellungen“ der Detailseite statt in einem Dialog. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { EmployeeDetailPage } from './EmployeeDetailPage'

const employee = {
  id: 7, location_id: 1, first_name: 'Erika', last_name: 'Muster', employee_number: '1001', active: true,
  login_email: 'erika@example.com', hr_role: null, hr_payroll_access: false, auto_break_enabled: true, has_pin: false,
  nfc_uid: null, hire_date: null, termination_date: null, birth_date: null, show_birthday_in_calendar: true, team_id: null,
  anonymized_at: null, two_factor_enabled: false,
}

function api() {
  return mockApi({
    'GET /employees/{employee_id}': employee,
    'GET /locations': [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }],
    'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true },
    'GET /teams': [],
    'GET /departments': [],
    'GET /employees': [],
    'PATCH /employees/{employee_id}': (init: ApiInit) => ({ ...employee, ...(init.body as object) }),
  })
}

function renderPage(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/employees/:employeeId" element={<EmployeeDetailPage />} />
    </Routes>,
    { route },
  )
}

describe('Reiter „Einstellungen“', () => {
  it('ersetzt den Knopf „Bearbeiten“ und speichert, ohne das Formular zu schließen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api()
    renderPage('/employees/7')
    await screen.findByText('1001')
    expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Einstellungen' }))
    const position = await screen.findByLabelText('Position')
    await userEvent.type(position, 'Lager')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.init.body).toMatchObject({ position: 'Lager' }))
    expect(await screen.findByText('Gespeichert.')).toBeInTheDocument()
    expect(screen.getByLabelText('Position')).toHaveValue('Lager')
  })

  it('öffnet den Reiter direkt über ?reiter=einstellungen und verwirft Änderungen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api()
    renderPage('/employees/7?reiter=einstellungen')
    const firstName = await screen.findByLabelText('Vorname')
    await waitFor(() => expect(firstName).toHaveValue('Erika'))
    await userEvent.clear(firstName)
    await userEvent.type(firstName, 'Erik')
    await userEvent.click(screen.getByRole('button', { name: 'Änderungen verwerfen' }))
    expect(screen.getByLabelText('Vorname')).toHaveValue('Erika')
  })

  it('speichert beim Öffnen nichts von selbst (HR-Berechtigung bleibt unangetastet)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = api()
    renderPage('/employees/7?reiter=einstellungen')
    await screen.findByText('HR-Berechtigung')
    await new Promise((resolve) => setTimeout(resolve, 200))
    expect(calls.filter((c) => c.method !== 'GET')).toEqual([])
  })

  it('zeigt Führungskräften keinen Reiter „Einstellungen“', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    api()
    renderPage('/employees/7?reiter=einstellungen')
    await screen.findByText('1001')
    expect(screen.queryByRole('tab', { name: 'Einstellungen' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Vorname')).not.toBeInTheDocument()
  })
})
