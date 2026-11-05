/** DATEV LODAS auf der Seite „Lohn-Export“: Zuordnung speichern, Vorschau mit Hinweisen, nur Admin. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { settings } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { PayrollExportPage } from '../../pages/PayrollExportPage'
import { DatevExportSection } from './DatevExportSection'

function lastBody(calls: ApiCall[], method: string) {
  return calls.filter((call) => call.method === method).at(-1)?.init.body as Record<string, unknown> | undefined
}

const nightRule = {
  id: 4,
  name: 'Nacht',
  kind: 'NIGHT',
  percent: 25,
  start_time: '22:00:00',
  end_time: '06:00:00',
  weekdays: [0, 1, 2, 3, 4, 5, 6],
  exclusive_group: null,
  active: true,
  wage_type: null,
}

describe('DATEV LODAS', () => {
  it('speichert Berater-/Mandantennummer und Lohnarten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /settings': settings(),
      'PATCH /settings': (init: ApiInit) => ({ ...settings(), ...(init.body as object) }),
      'GET /surcharge-rules': [nightRule],
      'PATCH /surcharge-rules/{rule_id}': { ...nightRule, wage_type: '1200' },
    })
    renderWithProviders(<DatevExportSection employeeIds={[1]} month="2026-08" />)

    expect(await screen.findByText(/zuerst Berater- und Mandantennummer/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /DATEV-Datei herunterladen/ })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Beraternummer'), '123')
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeDisabled() // < 4 Ziffern
    await userEvent.type(screen.getByLabelText('Beraternummer'), '4567')
    await userEvent.type(screen.getByLabelText('Mandantennummer'), '10001')
    await userEvent.type(screen.getByLabelText('Lohnart Ist-Stunden'), '1000')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(lastBody(calls, 'PATCH')).toMatchObject({
        datev_consultant_number: '1234567',
        datev_client_number: '10001',
        datev_hours_wage_type: '1000',
      }),
    )

    await userEvent.type(await screen.findByLabelText('Lohnart Nacht'), '1200')
    await userEvent.tab()
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'PATCH' && c.path === '/surcharge-rules/{rule_id}')).toBe(true),
    )
    expect(lastBody(calls, 'PATCH')).toMatchObject({ wage_type: '1200' })
  })

  it('zeigt die Vorschau mit Hinweisen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /settings': settings({ datev_consultant_number: '1234567', datev_client_number: '10001' }),
      'GET /surcharge-rules': [],
      'GET /payroll-export/datev/preview': {
        lines: [{ personnel_number: '12', name: 'Hourly, Hanna', wage_type: '1000', key: '01', value: 11, label: 'Ist-Stunden' }],
        warnings: ['Odd, Olga: Personalnummer „A-7“ ist nicht rein numerisch – nicht übertragen.'],
      },
    })
    renderWithProviders(<DatevExportSection employeeIds={[1, 2]} month="2026-08" />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Vorschau' })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau' }))
    expect(await screen.findByText('11,00 Std.')).toBeInTheDocument()
    expect(screen.getByText(/Personalnummer „A-7“/)).toBeInTheDocument()
    const call = calls.find((c) => c.path === '/payroll-export/datev/preview')
    expect(call?.init.params?.query).toEqual({ month: '2026-08', employee_ids: [1, 2] })
  })

  it('ist für HR auf der Seite nicht sichtbar', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /locations': [], 'GET /employees': [] })
    renderWithProviders(<PayrollExportPage />)
    expect(await screen.findByRole('button', { name: /CSV exportieren/ })).toBeInTheDocument()
    expect(screen.queryByText('DATEV LODAS')).not.toBeInTheDocument()
  })
})
