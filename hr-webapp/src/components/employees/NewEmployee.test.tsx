/** Dialog „Neuer Mitarbeiter“: Grunddaten oben, Arbeitszeitmodell ausdrücklich wählen, Seltenes eingeklappt. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { EmployeeFormDialog } from './EmployeeFormDialog'

const LOCATIONS = [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }] as never

function features(defaultDayMinutes: number[] | null) {
  return {
    'GET /features': {
      shift_planning_enabled: false,
      absence_requests_enabled: true,
      default_auto_break: true,
      default_show_birthday: true,
      default_day_minutes: defaultDayMinutes,
    },
    'GET /teams': [],
    'POST /employees': (init: ApiInit) => ({ id: 9, ...(init.body as object) }),
  }
}

function postBody(calls: ApiCall[]) {
  return calls.find((call) => call.method === 'POST')?.init.body as Record<string, unknown> | undefined
}

async function fillBasics() {
  await userEvent.type(screen.getByLabelText('Vorname'), 'Paula')
  await userEvent.type(screen.getByLabelText('Nachname'), 'Probe')
  await userEvent.type(screen.getByLabelText(/Personalnummer/), 'P1')
}

describe('Neuer Mitarbeiter', () => {
  it('nimmt standardmäßig das Standardmodell der Firma (nichts senden)', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(features([480, 480, 480, 480, 480, 0, 0]))
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    const choice = await screen.findByLabelText('Arbeitszeitmodell')
    await waitFor(() => expect(choice).toHaveValue('DEFAULT'))
    expect(screen.getByRole('option', { name: /Standard aus den Einstellungen \(Mo–Fr 8 Std\.\)/ })).toBeInTheDocument()
    await fillBasics()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(postBody(calls)).toMatchObject({ no_work_time_model: false }))
    expect(postBody(calls)).not.toHaveProperty('work_time_model')
  })

  it('legt bewusst ohne Modell oder nach Aufwand an – auch wenn ein Standard existiert', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(features([480, 480, 480, 480, 480, 0, 0]))
    const { unmount } = renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    await userEvent.selectOptions(screen.getByLabelText('Arbeitszeitmodell'), 'NONE')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(postBody(calls)).toMatchObject({ no_work_time_model: true }))
    unmount()

    const calls2 = mockApi(features(null))
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    await userEvent.selectOptions(screen.getByLabelText('Arbeitszeitmodell'), 'ON_DEMAND')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(postBody(calls2)).toMatchObject({ no_work_time_model: false, work_time_model: { on_demand: true } }))
  })

  it('verlangt bei „Stunden je Wochentag“ mindestens einen Tag', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(features(null))
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    // ohne Standard: vorbelegt ist „Kein Arbeitszeitmodell“
    await waitFor(() => expect(screen.getByLabelText('Arbeitszeitmodell')).toHaveValue('NONE'))
    await fillBasics()
    await userEvent.selectOptions(screen.getByLabelText('Arbeitszeitmodell'), 'DAYS')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/mindestens einen Wochentag/)).toBeInTheDocument()
    expect(postBody(calls)).toBeUndefined()
    await userEvent.type(screen.getByLabelText('Stunden Mo'), '7,5')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(postBody(calls)).toMatchObject({ work_time_model: { daily_hours: [7.5, 0, 0, 0, 0, 0, 0] } }))
  })

  it('klappt Seltenes beim Anlegen ein und beim Bearbeiten auf', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(features(null))
    const { unmount } = renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    const more = (await screen.findByText(/Weitere Angaben/)).closest('details')!
    const login = screen.getByText(/Login und Stempeln am Tablet/).closest('details')!
    expect(more).not.toHaveAttribute('open')
    expect(login).not.toHaveAttribute('open')
    unmount()

    const employee = {
      id: 7, location_id: 1, first_name: 'Hanna', last_name: 'Personal', employee_number: '1003', active: true,
      login_email: null, hr_role: null, hr_payroll_access: false, auto_break_enabled: true, has_pin: false, nfc_uid: null,
      hire_date: null, termination_date: null, birth_date: null, show_birthday_in_calendar: true, team_id: null, anonymized_at: null,
    } as never
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} employee={employee} locations={LOCATIONS} />)
    expect((await screen.findByText(/Weitere Angaben/)).closest('details')).toHaveAttribute('open')
    expect(screen.queryByLabelText('Arbeitszeitmodell')).not.toBeInTheDocument()
  })
})
