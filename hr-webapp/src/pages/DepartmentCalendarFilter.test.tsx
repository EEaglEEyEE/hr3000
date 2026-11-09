/** Kalender (Verwaltung): Filter nach Abteilungen samt „Ohne Abteilung“ statt nach Teams. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../test/utils'
import { TeamCalendarPage } from './TeamCalendarPage'

function calendarQueries(calls: ApiCall[]) {
  return calls.filter((call) => call.method === 'GET' && call.path === '/team-calendar').map((call) => call.init.params?.query)
}

describe('Kalender nach Abteilung', () => {
  it('filtert nach einer oder mehreren Abteilungen und nach „Ohne Abteilung“', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /locations': [],
      'GET /absence-types': [],
      'GET /departments': [
        { id: 1, name: 'Vertrieb', parent_id: null, leaders: [], employee_count: 2 },
        { id: 2, name: 'Innendienst', parent_id: 1, leaders: [], employee_count: 1 },
      ],
      'GET /team-calendar': [],
    })
    renderWithProviders(<TeamCalendarPage />)
    expect(await screen.findByText('Abteilungen:')).toBeInTheDocument()
    expect(screen.queryByText('Teams:')).not.toBeInTheDocument()
    await waitFor(() => expect(calendarQueries(calls).at(-1)?.department_id).toBeUndefined())

    await userEvent.click(screen.getByRole('button', { name: 'Vertrieb' }))
    await waitFor(() => expect(calendarQueries(calls).at(-1)?.department_id).toEqual([1]))
    await userEvent.click(screen.getByRole('button', { name: 'Ohne Abteilung' }))
    await waitFor(() => expect(calendarQueries(calls).at(-1)?.department_id).toEqual([1, 0]))
    expect(screen.getByRole('button', { name: 'Vertrieb' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Alle' }))
    await waitFor(() => expect(calendarQueries(calls).at(-1)?.department_id).toBeUndefined())
  })

  it('zeigt keinen Filter ohne Abteilungen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /locations': [], 'GET /absence-types': [], 'GET /departments': [], 'GET /team-calendar': [] })
    renderWithProviders(<TeamCalendarPage />)
    await screen.findByText(/Monatsübersicht/)
    expect(screen.queryByText('Abteilungen:')).not.toBeInTheDocument()
  })
})
