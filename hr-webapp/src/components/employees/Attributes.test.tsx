/** Personalakte → „Weitere Angaben“: Werte eigener Felder speichern, Verlauf mit Gültig-ab. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { AttributesTab } from './AttributesTab'

const sections = [
  {
    id: 1, name: 'Ausstattung', employee_access: 'VIEW', sort_order: 0, archived: false,
    attributes: [
      { id: 10, section_id: 1, label: 'T-Shirt', field_type: 'SELECT', options: ['S', 'M'], dated: false, sort_order: 0, archived: false },
      { id: 11, section_id: 1, label: 'Gehaltsband', field_type: 'NUMBER', options: [], dated: true, sort_order: 1, archived: false },
    ],
  },
]

describe('Weitere Angaben', () => {
  it('speichert eine Auswahl und einen datierten Wert', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /attribute-sections': sections,
      'GET /employees': [],
      'GET /employees/{employee_id}/attributes': [
        { attribute_id: 10, value: null, display: null, history: [] },
        { attribute_id: 11, value: '3', display: '3', history: [{ id: 5, value: '3', valid_from: '2026-01-01', created_at: '2026-01-01T00:00:00' }] },
      ],
      'PUT /employees/{employee_id}/attributes/{attribute_id}': [],
    })
    renderWithProviders(<AttributesTab employeeId={7} />)
    expect(await screen.findByText(/ab 1\.1\.2026: 3/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('T-Shirt'), 'M')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.init.body).toEqual({ value: 'M', valid_from: null }))

    await userEvent.clear(screen.getByLabelText('Gehaltsband'))
    await userEvent.type(screen.getByLabelText('Gehaltsband'), '4,5')
    await userEvent.type(screen.getByLabelText('Gehaltsband gültig ab'), '2026-12-01')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'PUT').at(-1)?.init.body).toEqual({ value: '4,5', valid_from: '2026-12-01' }),
    )
  })
})
