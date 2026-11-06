/** Seite „Lohnarten“: Zeitarten, Zuschläge und Zulagenarten an einer Stelle (nur Admin). */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../test/utils'
import { WageTypesPage } from './WageTypesPage'

const ITEMS: { item: string; label: string; wage_type: string | null }[] = (
  [
  ['WORKED', 'Gearbeitete Stunden', '1000'],
  ['VACATION', 'Urlaub', null],
  ['SICK', 'Krankheit', null],
  ['CHILD_SICK', 'Kind krank', null],
  ['SPECIAL_LEAVE', 'Sonderurlaub', null],
  ['PUBLIC_HOLIDAY', 'Feiertag', null],
  ['WORK_TIME', 'Arbeitszeit-Angaben (z. B. Homeoffice)', null],
  ['OVERTIME_PAYOUT', 'Ausgezahlte Überstunden', null],
  ] as [string, string, string | null][]
).map(([item, label, wage_type]) => ({ item, label, wage_type }))

function bodies(calls: ApiCall[], method: string, path: string) {
  return calls.filter((call) => call.method === method && call.path === path).map((call) => call.init.body as Record<string, unknown>)
}

describe('Lohnarten', () => {
  it('speichert Lohnarten je Zeitart, je Zuschlag und je Zulagenart', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /wage-types': { items: ITEMS },
      'PUT /wage-types': (init: ApiInit) => ({ items: ITEMS.map((i) => ({ ...i, wage_type: (init.body as { items: Record<string, string | null> }).items[i.item] ?? null })) }),
      'GET /surcharge-rules': [
        { id: 4, name: 'Nacht', kind: 'NIGHT', percent: 25, start_time: '22:00:00', end_time: '06:00:00', weekdays: [0, 1, 2, 3, 4, 5, 6], exclusive_group: null, active: true, wage_type: null },
      ],
      'PUT /surcharge-rules/{rule_id}/wage-type': {},
      'GET /pay-component-types': [{ id: 3, kind: 'ALLOWANCE', name: 'Fahrtkosten', wage_type: '2000', active: true, in_use: 2 }],
      'POST /pay-component-types': { id: 5, kind: 'ONE_TIME', name: 'Weihnachtsgeld', wage_type: '3000', active: true, in_use: 0 },
      'PATCH /pay-component-types/{type_id}': {},
    })
    renderWithProviders(<WageTypesPage />)

    await waitFor(() => expect(screen.getByLabelText('Lohnart Gearbeitete Stunden')).toHaveValue('1000'))
    await userEvent.type(screen.getByLabelText('Lohnart Urlaub'), '1100')
    await userEvent.click(screen.getByRole('button', { name: 'Lohnarten speichern' }))
    await waitFor(() => expect(bodies(calls, 'PUT', '/wage-types')).toHaveLength(1))
    expect(bodies(calls, 'PUT', '/wage-types')[0]).toMatchObject({ items: { WORKED: '1000', VACATION: '1100', SICK: null } })
    expect(await screen.findByText('Lohnarten gespeichert.')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Lohnart Zuschlag Nacht'), '1200')
    await userEvent.tab()
    await waitFor(() => expect(bodies(calls, 'PUT', '/surcharge-rules/{rule_id}/wage-type')[0]).toEqual({ wage_type: '1200' }))

    // Fahrtkosten wird verwendet: kein Löschen, aber Lohnart und aktiv änderbar
    expect(screen.queryByRole('button', { name: 'Fahrtkosten löschen' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Fahrtkosten aktiv' }))
    await waitFor(() => expect(bodies(calls, 'PATCH', '/pay-component-types/{type_id}')[0]).toEqual({ active: false }))

    await userEvent.selectOptions(screen.getByLabelText('Art'), 'ONE_TIME')
    await userEvent.type(screen.getByLabelText('Bezeichnung'), 'Weihnachtsgeld')
    await userEvent.type(screen.getByLabelText('Lohnart (optional)'), '3000')
    await userEvent.click(screen.getByRole('button', { name: 'Art hinzufügen' }))
    await waitFor(() =>
      expect(bodies(calls, 'POST', '/pay-component-types')[0]).toEqual({ kind: 'ONE_TIME', name: 'Weihnachtsgeld', wage_type: '3000' }),
    )
  })
})
