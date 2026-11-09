/** Mitarbeiter: Führungskraft kommt automatisch aus der Abteilungsleitung, je Person abweichend wählbar; kein Team mehr. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { employee } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { EmployeeForm, EmployeeFormDialog } from './EmployeeFormDialog'

const LOCATIONS = [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }] as never
const DEPARTMENTS = [
  {
    id: 1, name: 'Vertrieb', parent_id: null, employee_count: 1,
    leaders: [{ employee_id: 10, name: 'Tom Teamleiter', role: 'HEAD', deputy_rights: 'STANDBY', active: true }],
  },
  { id: 2, name: 'Lager', parent_id: null, leaders: [], employee_count: 0 },
]
const COLLEAGUES = [employee({ id: 10, first_name: 'Tom', last_name: 'Teamleiter' }), employee({ id: 11, first_name: 'Erika', last_name: 'Muster' })]

function routes() {
  return {
    'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true, default_day_minutes: null },
    'GET /departments': DEPARTMENTS,
    'GET /employees': COLLEAGUES,
    'POST /employees': (init: ApiInit) => ({ id: 9, ...(init.body as object) }),
    'PATCH /employees/{employee_id}': (init: ApiInit) => ({ ...employee({ id: 7 }), ...(init.body as object) }),
  }
}

function body(calls: ApiCall[], method: string) {
  return calls.filter((call) => call.method === method).at(-1)?.init.body as Record<string, unknown> | undefined
}

async function choose(label: string, option: string) {
  await userEvent.click(screen.getByRole('combobox', { name: label }))
  await userEvent.click(await screen.findByRole('option', { name: option }))
}

describe('Führungskraft am Mitarbeiter', () => {
  it('zeigt die automatische Führungskraft der gewählten Abteilung und sendet eine Ausnahme', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes())
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await userEvent.type(await screen.findByLabelText('Vorname'), 'Paula')
    await userEvent.type(screen.getByLabelText('Nachname'), 'Probe')
    await userEvent.type(screen.getByLabelText(/Personalnummer/), 'P1')
    expect(screen.queryByText('Team')).not.toBeInTheDocument()
    expect(screen.getByText(/Automatisch: keine \(ohne Abteilung\)\./)).toBeInTheDocument()

    await choose('Abteilung', 'Vertrieb')
    expect(screen.getByText(/Automatisch: Tom Teamleiter \(Leitung Vertrieb\)\./)).toBeInTheDocument()
    await choose('Abteilung', 'Lager')
    expect(screen.getByText(/Automatisch: keine \(Abteilung ohne Leitung\)\./)).toBeInTheDocument()

    await choose('Abweichende Führungskraft', 'Muster, Erika')
    expect(screen.getByText(/Ausnahme: gilt statt der Abteilungsleitung\./)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(body(calls, 'POST')).toMatchObject({ department_id: 2, supervisor_id: 11 }))
    expect(body(calls, 'POST')).not.toHaveProperty('team_id')
    expect(body(calls, 'POST')).not.toHaveProperty('approval_delegate_id')
    expect(screen.queryByText('Vertretung bei Genehmigungen')).not.toBeInTheDocument() // geht in den Stellvertretungen auf
  })

  it('setzt eine Ausnahme beim Bearbeiten wieder auf „wie Abteilung“ zurück', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes())
    const person = employee({ id: 7, first_name: 'Max', last_name: 'Beispiel', department_id: 1, supervisor_id: 11 })
    renderWithProviders(<EmployeeForm employee={person} locations={LOCATIONS} />)
    expect(await screen.findByText(/Ausnahme: gilt statt der Abteilungsleitung\./)).toBeInTheDocument()
    await choose('Abweichende Führungskraft', 'Wie Abteilung (automatisch)')
    expect(screen.getByText(/Automatisch: Tom Teamleiter \(Leitung Vertrieb\)\./)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(body(calls, 'PATCH')).toMatchObject({ clear_supervisor_id: true, department_id: 1 }))
    expect(body(calls, 'PATCH')).not.toHaveProperty('clear_team_id')
  })
})
