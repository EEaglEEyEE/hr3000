/** „Mein Bereich“ → „Teamkalender“: eigenes Team, Kollegen ausgegraut oder mit Art. */
import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { TeamCalendarPage } from './TeamCalendarPage'

afterEach(() => vi.restoreAllMocks())

describe('Teamkalender für Mitarbeiter', () => {
  it('lädt nur das eigene Team, ohne Standort- und Teamfilter', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const from = new Date()
    const calls = mockApi({
      'GET /absence-types': [],
      'GET /me/team-calendar': [
        { employee_id: 7, first_name: 'Max', last_name: 'Kollege', team_id: 1, days: [{ date: from.toISOString().slice(0, 10), status: 'ABSENCE', absence_type: null, is_birthday: false }] },
      ],
    })
    renderWithProviders(<TeamCalendarPage own />)
    expect(await screen.findByText('Kollege, Max')).toBeInTheDocument()
    expect(screen.queryByText('Alle Standorte')).not.toBeInTheDocument()
    expect(calls.some((c) => c.path === '/team-calendar')).toBe(false)
  })
})
