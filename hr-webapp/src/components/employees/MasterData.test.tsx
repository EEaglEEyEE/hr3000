/** Personalakte → „Stammdaten“: nur geänderte Felder speichern, Lohnfelder nur mit Freigabe,
 * Kostenstellen mit Summe 100 %. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { employee as employeeFixture } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { MasterDataTab } from './MasterDataTab'

const base = { private_email: null, phone: null, street: 'Hauptstr. 1', zip_code: null, city: 'Fulda', country: null,
  nationality: null, birth_place: null, birth_name: null, children_count: null, child_allowance: null, iban: null,
  bic: null, account_holder: null, tax_id: null, tax_class: null, church_tax: null, social_security_number: null,
  health_insurance: null }

describe('Stammdaten', () => {
  it('speichert nur geänderte Felder und zeigt ohne Freigabe keine Lohnfelder', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /employees/{employee_id}/personal-data': { ...base, payroll_visible: false },
      'PATCH /employees/{employee_id}/personal-data': { ...base, city: 'Kassel', payroll_visible: false },
      'GET /cost-centers': [],
    })
    renderWithProviders(<MasterDataTab employee={employeeFixture({ employment_status: 'LEAVE' })} />)
    expect(await screen.findByText('Auszeit')).toBeInTheDocument()
    expect(screen.queryByLabelText('IBAN')).not.toBeInTheDocument()
    const city = await screen.findByLabelText('Ort')
    await waitFor(() => expect(city).toHaveValue('Fulda'))
    await userEvent.clear(city)
    await userEvent.type(city, 'Kassel')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.init.body).toEqual({ city: 'Kassel' }))
  })

  it('verlangt bei Kostenstellen zusammen 100 %', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/personal-data': { ...base, payroll_visible: true },
      'GET /cost-centers': [{ id: 1, code: '100', name: 'Verwaltung', archived: false }],
      'PUT /employees/{employee_id}/cost-centers': [{ cost_center_id: 1, percent: 100 }],
    })
    renderWithProviders(
      <MasterDataTab employee={employeeFixture({ cost_centers: [{ cost_center_id: 1, percent: 60 }] })} />,
    )
    expect(await screen.findByText('Summe 60 %')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kostenstellen speichern' })).toBeDisabled()
    const percent = screen.getByLabelText('Anteil 1 in Prozent')
    await userEvent.clear(percent)
    await userEvent.type(percent, '100')
    await userEvent.click(screen.getByRole('button', { name: 'Kostenstellen speichern' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PUT')?.init.body).toEqual([{ cost_center_id: 1, percent: 100 }]),
    )
  })
})
