/** Abwesenheitsarten: Kategorie nachträglich ändern (mit Rückfrage), neue Kategorien wählbar. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { AbsenceTypesCard } from './AbsenceTypesCard'

const TYPES = [
  { id: 1, name: 'Urlaub', color: '#10b981', category: 'VACATION', requires_approval: false, employee_can_request: true, certificate_from_day: null, active: true, sort_order: 0 },
  { id: 7, name: 'Feiertag GfB', color: '#64748b', category: 'SPECIAL_LEAVE', requires_approval: false, employee_can_request: false, certificate_from_day: null, active: true, sort_order: 5 },
]

function setup() {
  loginAs({ kind: 'hr', role: 'ADMIN' })
  let types = TYPES.map((t) => ({ ...t }))
  const calls = mockApi({
    'GET /absence-types': () => types,
    'PATCH /absence-types/{type_id}': (init: ApiInit) => {
      types = types.map((t) => (t.id === init.params?.path?.type_id ? { ...t, ...(init.body as object) } : t))
      return types.find((t) => t.id === init.params?.path?.type_id)
    },
  })
  renderWithProviders(<AbsenceTypesCard />)
  return calls
}

describe('Abwesenheitsarten', () => {
  it('bietet alle Kategorien an – auch Arbeitszeit, Feiertag und Kind krank', async () => {
    setup()
    const select = (await screen.findByLabelText('Kategorie von Feiertag GfB')) as HTMLSelectElement
    expect(Array.from(select.options, (o) => o.textContent)).toEqual([
      'Urlaub', 'Krankheit', 'Sonderurlaub', 'Unbezahlt', 'Freizeitausgleich', 'Arbeitszeit', 'Feiertag', 'Kind krank',
    ])
    expect(select).toHaveValue('SPECIAL_LEAVE')
  })

  it('ändert die Kategorie nach Rückfrage', async () => {
    const calls = setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    await userEvent.selectOptions(await screen.findByLabelText('Kategorie von Feiertag GfB'), 'PUBLIC_HOLIDAY')
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('neu berechnet'))
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.init.body).toMatchObject({ category: 'PUBLIC_HOLIDAY' }))
    await waitFor(() => expect(screen.getByLabelText('Kategorie von Feiertag GfB')).toHaveValue('PUBLIC_HOLIDAY'))
  })

  it('ändert nichts, wenn die Rückfrage abgebrochen wird', async () => {
    const calls = setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    await userEvent.selectOptions(await screen.findByLabelText('Kategorie von Feiertag GfB'), 'WORK_TIME')
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
    expect(screen.getByLabelText('Kategorie von Feiertag GfB')).toHaveValue('SPECIAL_LEAVE')
  })
})
