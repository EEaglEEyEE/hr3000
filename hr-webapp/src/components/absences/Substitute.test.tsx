/** Vertretung im Antrag: Pflicht beim eigenen Antrag, Auswahl aus den Kolleginnen und Kollegen. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { AbsenceFormDialog } from './AbsenceFormDialog'

const VACATION = {
  id: 1, name: 'Urlaub', color: '#10b981', category: 'VACATION', requires_approval: true, employee_can_request: true,
  certificate_from_day: null, substitute_mode: 'REQUIRED', active: true, sort_order: 0,
}

afterEach(() => vi.restoreAllMocks())

describe('Vertretung', () => {
  it('verlangt beim eigenen Antrag eine Vertretung und sendet sie mit', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const calls = mockApi({
      'GET /absence-types': [VACATION],
      'GET /employees/{employee_id}/substitute-candidates': [{ id: 7, first_name: 'Max', last_name: 'Vertreter' }],
      'POST /absences': (init: ApiInit) => ({ id: 9, ...(init.body as object) }),
    })
    const onOpenChange = vi.fn()
    renderWithProviders(<AbsenceFormDialog open onOpenChange={onOpenChange} employeeId={5} selfService />)

    const select = await screen.findByLabelText('Vertretung')
    expect(select).toBeRequired()
    await screen.findByRole('option', { name: 'Max Vertreter' })
    await userEvent.selectOptions(select, '7')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(calls.find((c) => c.method === 'POST')?.init.body).toMatchObject({ substitute_employee_id: 7 })
  })

  it('zeigt kein Feld, wenn die Art keine Vertretung abfragt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /absence-types': [{ ...VACATION, substitute_mode: 'NONE' }] })
    renderWithProviders(<AbsenceFormDialog open onOpenChange={vi.fn()} employeeId={5} />)
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Urlaub'))
    expect(screen.queryByLabelText(/Vertretung/)).not.toBeInTheDocument()
  })
})
