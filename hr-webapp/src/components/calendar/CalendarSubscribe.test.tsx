/** Kalender-Abo: Link erzeugen und anzeigen. */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { CalendarSubscribe } from './CalendarSubscribe'

afterEach(() => vi.restoreAllMocks())

describe('Kalender-Abo', () => {
  it('zeigt den privaten Abo-Link', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({ 'POST /me/calendar-token': { path: '/api/calendar/geheim.ics' } })
    renderWithProviders(<CalendarSubscribe />)
    await userEvent.click(screen.getByRole('button', { name: 'Kalender abonnieren (iCal)' }))
    expect(await screen.findByLabelText('Abo-Link')).toHaveValue(`${window.location.origin}/api/calendar/geheim.ics`)
  })
})
