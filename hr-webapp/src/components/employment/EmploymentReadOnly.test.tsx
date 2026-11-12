/** „Vertrag & Vergütung“ mit eigener Rolle: Stufe „Ansehen“ zeigt die Daten ohne Anlegen-, Beenden-
 * und Löschen-Schaltflächen; „Bearbeiten“ bleibt wie bisher. */
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { EmploymentTab } from './EmploymentTab'

const contract = {
  id: 11,
  employee_id: 7,
  valid_from: '2026-01-01',
  valid_to: null,
  contract_type: 'PERMANENT',
  job_title: 'Disponentin',
  probation_end: null,
  fixed_term_end: null,
  notice_period: null,
  annual_vacation_days: null,
}
const compensation = {
  id: 21,
  employee_id: 7,
  valid_from: '2026-01-01',
  valid_to: null,
  pay_type: 'MONTHLY',
  amount: 3200,
  currency: 'EUR',
  note: null,
}
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

function setup() {
  loginAs({ kind: 'hr', role: 'HR' })
  return mockApi({
    'GET /employees/{employee_id}/contracts': [contract],
    'GET /employees/{employee_id}/compensation': [compensation],
    'GET /employees/{employee_id}/pay-components': [allowance],
    'GET /pay-component-types': [],
  })
}

const NOTE = 'Nur Ansicht – deine Rolle darf hier nichts ändern.'

describe('Vertrag & Vergütung: Nur-Lese-Modus', () => {
  it('zeigt mit „Vergütung: Ansehen“ die Beträge, aber keine Schaltflächen zum Ändern', async () => {
    setup()
    renderWithProviders(<EmploymentTab employeeId={7} isAdmin canEditPay={false} />)

    expect(await screen.findByText('3.200,00 EUR / Monat')).toBeInTheDocument()
    expect(await screen.findByText('Fahrtkosten')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Neue Vergütung' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Neue Zulage' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Neue Einmalzahlung' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Beenden' })).not.toBeInTheDocument()
    expect(screen.getAllByText(NOTE)).toHaveLength(2)
    // Vertragsdaten bleiben bearbeitbar: einziges Löschen-Symbol gehört zum Vertrag
    expect(screen.getByRole('button', { name: /Neuer Vertragsabschnitt/ })).toBeInTheDocument()
    expect(screen.getAllByTitle('Löschen')).toHaveLength(1)
  })

  it('zeigt mit „Mitarbeiter: Ansehen“ die Vertragsdaten ohne Anlegen und Löschen', async () => {
    setup()
    renderWithProviders(<EmploymentTab employeeId={7} isAdmin canEditContract={false} />)

    expect(await screen.findByText('Disponentin')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Neuer Vertragsabschnitt/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Neue Vergütung' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Neue Zulage' })).toBeInTheDocument()
    expect(screen.getAllByText(NOTE)).toHaveLength(1)
    // Löschen bleibt nur bei Vergütung und Zulage
    expect(await screen.findAllByTitle('Löschen')).toHaveLength(2)
  })

  it('ist komplett nur lesbar, wenn beide Bereiche nur „Ansehen“ haben', async () => {
    setup()
    renderWithProviders(<EmploymentTab employeeId={7} isAdmin canEditContract={false} canEditPay={false} />)

    expect(await screen.findByText('Disponentin')).toBeInTheDocument()
    expect(await screen.findByText('Fahrtkosten')).toBeInTheDocument()
    expect(screen.queryByTitle('Löschen')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Neu/ })).not.toBeInTheDocument()
    expect(screen.getAllByText(NOTE)).toHaveLength(3)
  })

  it('bleibt ohne Angabe voll bearbeitbar (Admin, HR ohne eigene Rolle)', async () => {
    setup()
    renderWithProviders(<EmploymentTab employeeId={7} isAdmin />)

    expect(await screen.findByText('Fahrtkosten')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Neuer Vertragsabschnitt/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Neue Vergütung' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Beenden' })).toBeInTheDocument()
    expect(await screen.findAllByTitle('Löschen')).toHaveLength(3)
    expect(screen.queryByText(NOTE)).not.toBeInTheDocument()
  })

  it('zeigt ohne Vergütungsrecht weder Vergütung noch Zulagen', async () => {
    setup()
    renderWithProviders(<EmploymentTab employeeId={7} isAdmin={false} canEditContract={false} />)

    expect(await screen.findByText('Disponentin')).toBeInTheDocument()
    expect(screen.queryByText('Vergütung')).not.toBeInTheDocument()
    expect(screen.queryByText('Fahrtkosten')).not.toBeInTheDocument()
  })
})
