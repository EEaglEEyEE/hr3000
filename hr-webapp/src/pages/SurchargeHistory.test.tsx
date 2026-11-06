/** Zuschlagsregeln bearbeiten: Änderung an Satz/Zeitfenster gilt ab Stichtag, frühere Fassungen anzeigbar. */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../test/utils'
import { SurchargeRulesPage } from './SurchargeRulesPage'

const night = {
  id: 4, name: 'Nacht', kind: 'NIGHT', percent: 25, start_time: '22:00:00', end_time: '06:00:00', weekdays: [0, 1, 2, 3, 4, 5, 6],
  exclusive_group: null, active: true, wage_type: null, valid_from: null, valid_to: null, family_id: 4,
}

function lastPatch(calls: ApiCall[]) {
  return calls.filter((call) => call.method === 'PATCH').at(-1)?.init.body as Record<string, unknown> | undefined
}

describe('Zuschlagsregeln mit Verlauf', () => {
  it('ändert den Satz ab einem Stichtag', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /surcharge-rules': [night],
      'PATCH /surcharge-rules/{rule_id}': { ...night, id: 5, percent: 40, valid_from: '2026-12-01' },
    })
    renderWithProviders(<SurchargeRulesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Nacht bearbeiten' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByLabelText('Änderung gilt ab')).not.toBeInTheDocument()  // erst bei geändertem Satz
    await userEvent.clear(within(dialog).getByLabelText('Zuschlag in %'))
    await userEvent.type(within(dialog).getByLabelText('Zuschlag in %'), '40')
    fireEvent.change(within(dialog).getByLabelText('Änderung gilt ab'), { target: { value: '2026-12-01' } })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(lastPatch(calls)).toMatchObject({ percent: 40, valid_from: '2026-12-01', start_time: '22:00:00', clear_exclusive_group: true }),
    )
  })

  it('nur Name geändert: ohne Stichtag', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /surcharge-rules': [night], 'PATCH /surcharge-rules/{rule_id}': { ...night, name: 'Nachtarbeit' } })
    renderWithProviders(<SurchargeRulesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Nacht bearbeiten' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.clear(within(dialog).getByLabelText('Name'))
    await userEvent.type(within(dialog).getByLabelText('Name'), 'Nachtarbeit')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ name: 'Nachtarbeit', percent: 25 }))
    expect(lastPatch(calls)).not.toHaveProperty('valid_from')
  })

  it('zeigt frühere Fassungen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /surcharge-rules': [
        { ...night, valid_to: '2026-11-30' },
        { ...night, id: 5, percent: 40, valid_from: '2026-12-01', family_id: 4 },
      ],
    })
    renderWithProviders(<SurchargeRulesPage />)
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Frühere Fassungen anzeigen' }))
    await waitFor(() => expect(calls.at(-1)?.init.params?.query).toEqual({ include_history: true }))
    expect(await screen.findByText('bis 30.11.2026')).toBeInTheDocument()
    expect(screen.getByText('ab 1.12.2026')).toBeInTheDocument()
  })
})
