/** Genehmigungsketten: Auswahl je Abwesenheitsart und Anzeige, bei wem ein Antrag liegt. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AbsenceTypesCard } from '../settings/AbsenceTypesCard'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'

const vacation = {
  id: 1, name: 'Urlaub', color: '#22c55e', category: 'VACATION', requires_approval: true, employee_can_request: true,
  certificate_from_day: null, substitute_mode: 'NONE', comment_required: false, calendar_visibility: 'GREY',
  approval_chain: 'DEFAULT', active: true, sort_order: 0,
}

describe('Genehmigung je Abwesenheitsart', () => {
  it('stellt die Kette um', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /absence-types': [vacation],
      'PATCH /absence-types/{type_id}': { ...vacation, approval_chain: 'SUPERVISOR_HR' },
    })
    renderWithProviders(<AbsenceTypesCard />)
    const select = await screen.findByLabelText('Genehmigung bei Urlaub')
    await userEvent.selectOptions(select, 'SUPERVISOR_HR')
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.init.body).toMatchObject({ approval_chain: 'SUPERVISOR_HR' }),
    )
  })
})
