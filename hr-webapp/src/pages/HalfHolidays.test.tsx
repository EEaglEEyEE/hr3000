/** Halbe Feiertage im Feiertagskalender: anlegen mit „Halber Tag“, Hinweis in der Liste. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { HolidaysPage } from './HolidaysPage'

beforeEach(() => loginAs({ kind: 'hr', role: 'HR' }))

describe('Feiertagskalender', () => {
  it('legt einen halben Feiertag an und kennzeichnet ihn in der Liste', async () => {
    const calls = mockApi({
      'GET /locations': [],
      'GET /holidays': [
        { id: 1, date: '2026-12-24', name: 'Heiligabend', location_ids: [], half_day: true },
        { id: 2, date: '2026-12-25', name: '1. Weihnachtstag', location_ids: [], half_day: false },
      ],
      'POST /holidays': { id: 3, date: '2026-12-31', name: 'Silvester', location_ids: [], half_day: true },
    })
    renderWithProviders(<HolidaysPage />)

    expect(await screen.findByText('Heiligabend')).toBeInTheDocument()
    expect(screen.getAllByText('(halber Tag)')).toHaveLength(1)

    await userEvent.type(screen.getByLabelText('Datum'), '2026-12-31')
    await userEvent.type(screen.getByLabelText('Name'), 'Silvester')
    await userEvent.click(screen.getByLabelText('Halber Tag'))
    await userEvent.click(screen.getByRole('button', { name: /Feiertag hinzufügen/ }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path === '/holidays')?.init.body).toMatchObject({
        date: '2026-12-31',
        name: 'Silvester',
        half_day: true,
      }),
    )
  })
})
