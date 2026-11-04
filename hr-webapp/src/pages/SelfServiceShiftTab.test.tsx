/** "Mein Bereich": Reiter Schichtplanung nur, wenn die Firma Schichtplanung nutzt. */
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { dashboard } from '../test/fixtures'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { SelfServicePage } from './SelfServicePage'

describe('Mein Bereich', () => {
  it.each([
    { enabled: false, visible: false },
    { enabled: true, visible: true },
  ])('Schichtplanung genutzt: $enabled -> Reiter sichtbar: $visible', async ({ enabled, visible }) => {
    loginAs({ kind: 'employee', employeeId: 7 })
    mockApi({
      'GET /employees/{employee_id}': { id: 7, first_name: 'Erika', last_name: 'Muster', location_id: 1, active: true },
      'GET /dashboard': dashboard({ shift_planning_enabled: enabled }),
    })
    renderWithProviders(<SelfServicePage />, { route: '/mein-bereich' })
    expect(await screen.findByRole('tab', { name: 'Übersicht' })).toBeInTheDocument()
    if (visible) expect(await screen.findByRole('tab', { name: 'Schichtplanung' })).toBeInTheDocument()
    else expect(screen.queryByRole('tab', { name: 'Schichtplanung' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Passwort ändern/ })).toBeInTheDocument()
  })
})
