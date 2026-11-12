/** Dialog „Neuer Mitarbeiter“: Grunddaten oben, Arbeitszeitmodell ausdrücklich wählen, Seltenes eingeklappt. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { EmployeeForm, EmployeeFormDialog } from './EmployeeFormDialog'

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

  it('weist beim Anlegen ein Arbeitszeitmodell zu', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      ...features([480, 480, 480, 480, 480, 0, 0]),
      'GET /work-time-profiles': [{ id: 4, name: 'Vollzeit Büro' }],
    })
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    await userEvent.selectOptions(await screen.findByLabelText('Arbeitszeitmodell'), 'Arbeitszeitmodell „Vollzeit Büro“')
    expect(screen.getByText(/Folgt automatisch den Änderungen des Modells/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(postBody(calls)).toMatchObject({ no_work_time_model: false, work_time_profile_id: 4 }))
    expect(postBody(calls)).not.toHaveProperty('work_time_model')
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

  it('sendet abgegoltene Überstunden nur, wenn sie eingetragen sind', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(features(null))
    const { unmount } = renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    // das Feld gibt es nur bei „Stunden je Wochentag“
    expect(screen.queryByLabelText(/abgegoltene Überstunden/)).not.toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Arbeitszeitmodell'), 'DAYS')
    await userEvent.type(screen.getByLabelText('Stunden Mo'), '8')
    await userEvent.type(screen.getByLabelText(/abgegoltene Überstunden/), '7,5')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(postBody(calls)).toMatchObject({ work_time_model: { daily_hours: [8, 0, 0, 0, 0, 0, 0], settled_overtime_hours: 7.5 } }),
    )
    unmount()

    const calls2 = mockApi(features(null))
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    await userEvent.selectOptions(screen.getByLabelText('Arbeitszeitmodell'), 'DAYS')
    await userEvent.type(screen.getByLabelText('Stunden Mo'), '8')
    await userEvent.type(screen.getByLabelText(/abgegoltene Überstunden/), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(postBody(calls2)).toBeDefined())
    expect((postBody(calls2) as { work_time_model: object }).work_time_model).not.toHaveProperty('settled_overtime_hours')
  })

  it.each(['abc', '-1', '100,5'])('lehnt abgegoltene Überstunden „%s“ ab, bevor gespeichert wird', async (value) => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(features(null))
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    await userEvent.selectOptions(screen.getByLabelText('Arbeitszeitmodell'), 'DAYS')
    await userEvent.type(screen.getByLabelText('Stunden Mo'), '8')
    await userEvent.type(screen.getByLabelText(/abgegoltene Überstunden/), value)
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/zwischen 0 und 100 Stunden je Monat/)).toBeInTheDocument()
    expect(postBody(calls)).toBeUndefined()
  })

  it('nennt den mehrwöchigen Turnus als Möglichkeit im Reiter „Arbeitszeit“', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(features(null))
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    expect(await screen.findByText(/mehrwöchiger Turnus/)).toBeInTheDocument()
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
      hire_date: null, termination_date: null, birth_date: null, show_birthday_in_calendar: true, department_id: null, anonymized_at: null,
    } as never
    renderWithProviders(<EmployeeForm employee={employee} locations={LOCATIONS} />)
    expect((await screen.findByText(/Weitere Angaben/)).closest('details')).toHaveAttribute('open')
    expect(screen.queryByLabelText('Arbeitszeitmodell')).not.toBeInTheDocument()
  })
})
