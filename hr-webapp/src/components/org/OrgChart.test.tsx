/** Organigramm aus der Führungskraft je Mitarbeiter und Abteilungen als Baum. */
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { DepartmentsPage } from '../../pages/DepartmentsPage'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { OrgChart } from './OrgChart'

const person = (id: number, first: string, supervisor: number | null, position: string | null = null) => ({
  employee_id: id, first_name: first, last_name: 'Test', position, department_id: null,
  department: position ? 'Vertrieb' : null, supervisor_id: supervisor,
})

describe('Organigramm', () => {
  it('zeigt Führungskräfte oben und ihre Mitarbeiter darunter, Suche filtert', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /org-chart': [person(1, 'Bea', null, 'Leitung'), person(2, 'Erika', 1), person(3, 'Max', 2), person(4, 'Solo', null)],
    })
    renderWithProviders(<OrgChart />)
    const bea = (await screen.findByText('Bea Test')).closest('li')!
    expect(within(bea).getByText('Leitung · Vertrieb')).toBeInTheDocument()
    expect(within(bea).getByText('Erika Test')).toBeInTheDocument()
    expect(within(bea).getByText('2')).toBeInTheDocument() // zwei im Bereich
    expect(within(bea).getByText('Max Test')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Im Organigramm suchen'), 'max')
    expect(screen.getByText('Max Test')).toBeInTheDocument()
    expect(screen.queryByText('Solo Test')).not.toBeInTheDocument()
  })
})

describe('Abteilungen', () => {
  it('zeigt verschachtelte Abteilungen eingerückt und legt neue an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /departments': [
        { id: 1, name: 'Vertrieb', parent_id: null, employee_count: 3 },
        { id: 2, name: 'Innendienst', parent_id: 1, employee_count: 1 },
      ],
      'POST /departments': { id: 3, name: 'Lager', parent_id: null, employee_count: 0 },
    })
    renderWithProviders(<DepartmentsPage />)
    const rows = await screen.findAllByRole('row')
    expect(rows.map((row) => row.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('Vertrieb3'), expect.stringContaining('└Innendienst1')]),
    )
    await userEvent.click(screen.getByRole('button', { name: /Neue Abteilung/ }))
    await userEvent.type(screen.getByLabelText('Name'), 'Lager')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(calls.find((c) => c.method === 'POST')?.init.body).toEqual({ name: 'Lager', parent_id: null })
  })
})
