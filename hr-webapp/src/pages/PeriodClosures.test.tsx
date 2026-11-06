/** Monatsabschluss: drei Zustände, Hinweis auf offene Anträge vor dem Vorlegen. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { PeriodClosuresPage } from './PeriodClosuresPage'

const row = { employee_id: 7, first_name: 'Erika', last_name: 'Muster', employee_number: 'E1', status: null, closure_id: null, delta_minutes: null, dispute_reason: null, open_day_count: 0 }

afterEach(() => vi.restoreAllMocks())

describe('Monatsabschluss', () => {
  it('fragt bei offenen Anträgen nach und legt dann trotzdem vor', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    let attempts = 0
    const calls = mockApi({
      'GET /period-closures': [row],
      'POST /employees/{employee_id}/period-closures/{year}/{month}/submit': (init: ApiInit) => {
        attempts += 1
        if (!(init.body as { ignore_open_requests?: boolean }).ignore_open_requests) {
          return new ApiFailure(409, 'OPEN_REQUESTS_PRESENT', 'Für den Monat ist noch offen: 1 Abwesenheitsantrag')
        }
        return { ...row, status: 'SUBMITTED' }
      },
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<PeriodClosuresPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Vorlegen' }))
    await waitFor(() => expect(attempts).toBe(2))
    expect(confirm.mock.calls[0][0]).toMatch(/1 Abwesenheitsantrag[\s\S]*Trotzdem vorlegen/)
    const last = calls.filter((c) => c.method === 'POST').at(-1)
    expect(last?.init.body).toEqual({ ignore_open_days: true, ignore_open_requests: true })
  })

  it('kennt keinen eigenen Status „bestätigt“ mehr: Abgeschlossen öffnen nur Admins', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /period-closures': [{ ...row, status: 'CLOSED', closure_id: 3 }] })
    renderWithProviders(<PeriodClosuresPage />)
    expect(await screen.findByText('Abgeschlossen')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Wieder öffnen' })).not.toBeInTheDocument()
  })
})
