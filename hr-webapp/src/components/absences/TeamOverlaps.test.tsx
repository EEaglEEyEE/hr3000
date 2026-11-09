/** Überschneidungen im Team: Hinweis im Antrag und bei den offenen Urlaubsanträgen. */
import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { AbsenceFormDialog } from './AbsenceFormDialog'
import { PendingAbsencesPanel } from './PendingAbsencesPanel'

const VACATION = {
  id: 1, name: 'Urlaub', color: '#10b981', category: 'VACATION', requires_approval: true, employee_can_request: true,
  certificate_from_day: null, substitute_mode: 'NONE', active: true, sort_order: 0,
}
const OVERLAP = { employee_id: 7, name: 'Max Kollege', date_from: '2026-12-21', date_to: '2026-12-23', half_day: false, pending: true, type_name: 'Urlaub' }

afterEach(() => vi.restoreAllMocks())

describe('Überschneidungen im Team', () => {
  it('zeigt im Antrag, wer im Team gleichzeitig fehlt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /absence-types': [VACATION], 'GET /employees/{employee_id}/team-overlaps': [OVERLAP] })
    renderWithProviders(<AbsenceFormDialog open onOpenChange={vi.fn()} employeeId={5} />)
    expect(await screen.findByText('Im Team gleichzeitig abwesend:')).toBeInTheDocument()
    expect(screen.getByText(/Max Kollege: 21\.12\.2026–23\.12\.2026 \(Urlaub\) – beantragt/)).toBeInTheDocument()
  })

  it('zeigt bei offenen Anträgen Resturlaub und Überschneidungen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /absence-types': [VACATION],
      'GET /employees': [{ id: 5, first_name: 'Erika', last_name: 'Muster' }],
      'GET /absences/pending': [
        {
          id: 3, employee_id: 5, type: 'VACATION', absence_type_id: 1, date_from: '2026-12-22', date_to: '2026-12-23',
          half_day: false, duration_minutes: null, created_by_account_id: 5, note: null,
          substitute_employee_id: null, substitute_name: null, approval_status: 'PENDING', decided_by: null,
          decided_by_employee_id: null, decided_at: null, team_overlaps: [OVERLAP], remaining_vacation_days: 12.5,
        },
      ],
    })
    renderWithProviders(<PendingAbsencesPanel />)
    expect(await screen.findByText('Resturlaub 2026: 12,5 Tage')).toBeInTheDocument()
    expect(screen.getByText(/Gleichzeitig abwesend: Max Kollege/)).toBeInTheDocument()
  })
})
