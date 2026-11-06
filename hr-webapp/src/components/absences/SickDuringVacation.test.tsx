/** Krankheit im Urlaub: Rückfrage und Rückgabe der Urlaubstage (§ 9 BUrlG). */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { AbsenceFormDialog } from './AbsenceFormDialog'

const TYPES = [
  { id: 2, name: 'Krankheit', color: '#ef4444', category: 'SICK', requires_approval: false, employee_can_request: true, certificate_from_day: 3, active: true, sort_order: 1 },
]

afterEach(() => vi.restoreAllMocks())

describe('Krankheit im Urlaub', () => {
  it('fragt nach und gibt die Urlaubstage zurück', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /absence-types': TYPES,
      'POST /absences': (init: ApiInit) =>
        (init.body as { split_vacation?: boolean }).split_vacation
          ? { id: 9, ...(init.body as object) }
          : new ApiFailure(409, 'ABSENCE_OVERLAP_VACATION', 'In diesem Zeitraum ist Urlaub eingetragen (10.08.2026–21.08.2026).'),
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onOpenChange = vi.fn()
    renderWithProviders(<AbsenceFormDialog open onOpenChange={onOpenChange} employeeId={5} />)
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Krankheit'))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(confirm.mock.calls[0][0]).toContain('Urlaubstage für die Krankheitstage zurückgeben?')
    const posts = calls.filter((call) => call.method === 'POST')
    expect(posts).toHaveLength(2)
    expect(posts[1].init.body).toMatchObject({ split_vacation: true })
  })

  it('lässt bei Ablehnung alles, wie es ist', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /absence-types': TYPES,
      'POST /absences': new ApiFailure(409, 'ABSENCE_OVERLAP_VACATION', 'In diesem Zeitraum ist Urlaub eingetragen.'),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWithProviders(<AbsenceFormDialog open onOpenChange={vi.fn()} employeeId={5} />)
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Krankheit'))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/In diesem Zeitraum ist Urlaub eingetragen/)).toBeInTheDocument()
  })
})
