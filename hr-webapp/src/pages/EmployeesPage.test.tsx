/** Mitarbeiterliste: Spalte und Filter „Abteilung“ (eine Abteilung schließt ihre Unterabteilungen ein). */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { employee } from '../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../test/utils'
import { EmployeesPage } from './EmployeesPage'

const departments = [
  { id: 1, name: 'Vertrieb', parent_id: null },
  { id: 2, name: 'Innendienst', parent_id: 1 },
  { id: 3, name: 'IT', parent_id: null },
]

function employeeQueries(calls: ApiCall[]) {
  return calls.filter((call) => call.method === 'GET' && call.path === '/employees').map((call) => call.init.params?.query)
}

async function choose(trigger: HTMLElement, option: string) {
  await userEvent.click(trigger)
  await userEvent.click(await screen.findByRole('option', { name: option }))
}

describe('Mitarbeiterliste nach Abteilung', () => {
  it('zeigt die Abteilung je Mitarbeiter und filtert danach', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees': [
        employee({ id: 1, first_name: 'Ines', last_name: 'Innen', department_id: 2 }),
        employee({ id: 2, first_name: 'Olaf', last_name: 'Ohne', department_id: null }),
      ],
      'GET /locations': [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }],
      'GET /departments': departments,
    })
    renderWithProviders(<EmployeesPage />)
    expect(await screen.findByRole('columnheader', { name: 'Abteilung' })).toBeInTheDocument()
    const ines = (await screen.findByText('Innen, Ines')).closest('tr')!
    const cell = within(ines).getByText('Innendienst')
    expect(cell.closest('td')).toHaveAttribute('title', 'Vertrieb › Innendienst')
    expect(within(screen.getByText('Ohne, Olaf').closest('tr')!).getAllByText('–').length).toBeGreaterThan(0)

    const filter = screen.getByRole('combobox', { name: 'Abteilung' })
    // Unterabteilungen stehen unter ihrer Abteilung (Pfad)
    await userEvent.click(filter)
    const options = (await screen.findAllByRole('option')).map((o) => o.textContent)
    expect(options).toEqual(['Alle Abteilungen', 'Ohne Abteilung', 'IT', 'Vertrieb', 'Vertrieb › Innendienst'])
    await userEvent.click(screen.getByRole('option', { name: 'Vertrieb' }))
    await waitFor(() => expect(employeeQueries(calls).at(-1)).toMatchObject({ department_id: 1 }))
    expect(employeeQueries(calls).at(-1)?.without_department).toBeUndefined()

    await choose(filter, 'Ohne Abteilung')
    await waitFor(() => expect(employeeQueries(calls).at(-1)).toMatchObject({ without_department: true, department_id: undefined }))

    await choose(filter, 'Alle Abteilungen')
    await waitFor(() => expect(employeeQueries(calls).at(-1)).toMatchObject({ department_id: undefined, without_department: undefined }))
  })

  it('zeigt keinen Abteilungsfilter, solange es keine Abteilungen gibt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees': [employee({ id: 1, first_name: 'Olaf', last_name: 'Ohne' })],
      'GET /locations': [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }],
      'GET /departments': [],
    })
    renderWithProviders(<EmployeesPage />)
    await screen.findByText('Ohne, Olaf')
    expect(screen.queryByRole('combobox', { name: 'Abteilung' })).not.toBeInTheDocument()
  })
})
