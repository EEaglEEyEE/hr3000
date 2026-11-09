/** Nachweis zu einer Abwesenheit hochladen und Pflichtkommentar im Antrag. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { AbsenceFormDialog } from './AbsenceFormDialog'
import { AbsencesTab } from './AbsencesTab'

const SICK = {
  id: 2, name: 'Krank', color: '#ef4444', category: 'SICK', requires_approval: false, employee_can_request: true,
  certificate_from_day: 3, substitute_mode: 'NONE', comment_required: false, active: true, sort_order: 1,
}
const ABSENCE = {
  id: 11, employee_id: 5, type: 'SICK', absence_type_id: 2, date_from: '2026-11-02', date_to: '2026-11-06', half_day: false,
  duration_minutes: null, created_by_account_id: 1, note: null, substitute_employee_id: null,
  substitute_name: null, certificate_document_id: null, approval_status: 'APPROVED', decided_by: null,
  decided_by_employee_id: null, decided_at: null,
}

afterEach(() => vi.restoreAllMocks())

describe('Nachweis', () => {
  it('lädt einen Nachweis zur Abwesenheit hoch', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({
      'GET /absence-types': [SICK],
      'GET /employees/{employee_id}/absences': [ABSENCE],
      'GET /employees/{employee_id}/leave-entitlement': { year: 2026, entitled_days: 30, carried_over_days: 0, used_days: 0, remaining_days: 30 },
      'GET /employees/{employee_id}/leave-adjustments': [],
    })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))
    renderWithProviders(<AbsencesTab employeeId={5} readOnly allowSelfCreate />)

    const input = await screen.findByLabelText(/Nachweis hochladen für Krank/)
    await userEvent.upload(input, new File(['%PDF-1.4'], 'au.pdf', { type: 'application/pdf' }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe('/api/absences/11/certificate')
    expect((init as RequestInit).method).toBe('POST')
  })

  it('verlangt einen Kommentar, wenn die Art es vorgibt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /absence-types': [{ ...SICK, id: 3, name: 'Sonderurlaub', category: 'SPECIAL_LEAVE', comment_required: true }] })
    renderWithProviders(<AbsenceFormDialog open onOpenChange={vi.fn()} employeeId={5} />)
    expect(await screen.findByLabelText('Notiz')).toBeRequired()
  })
})
