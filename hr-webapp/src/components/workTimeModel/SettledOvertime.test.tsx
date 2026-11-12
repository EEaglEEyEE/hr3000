/** Monatlich mit dem Gehalt abgegoltene Überstunden: Eingabe im Arbeitszeitmodell (am Mitarbeiter und
 *  in den Arbeitszeitmodellen), Anzeige im gültigen Modell, im Verlauf und in der Kontoansicht. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { WorkTimeProfilesPage } from '../../pages/WorkTimeProfilesPage'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { TimesheetTab } from '../timesheet/TimesheetTab'
import { describeVersion, type ModelSource } from './modelText'
import { WorkTimeModelTab } from './WorkTimeModelTab'

const fields = {
  weekly_minutes: 2400,
  daily_minutes: 480,
  weekdays: [0, 1, 2, 3, 4],
  day_minutes: [480, 480, 480, 480, 480, 0, 0],
  uneven: false,
  rotation_minutes: null,
  rotation_start: null,
  settled_overtime_minutes: 600,
  flexible: false,
  on_demand: false,
  monthly_cap_minutes: null,
  monthly_minutes: null,
  target_from_template: false,
  break_minutes: null,
  break_after_minutes: 0,
  break_start: null,
  break_end: null,
  break_from_template: false,
  shift_template_id: null,
  shift_template_name: null,
  shift_start: null,
  shift_end: null,
  core_time_mode: 'TENANT',
  core_time_start: null,
  core_time_end: null,
  core_time_days: null,
  flex_frame_mode: 'TENANT',
  flex_frame_start: null,
  flex_frame_end: null,
  late_tolerance_minutes: null,
  profile_id: null,
  profile_name: null,
}

const model = { ...fields, employee_id: 7, configured: true, is_work_time_model: true, valid_from: '2026-10-01' }
const withoutLimit = { ...model, settled_overtime_minutes: null }

function lastBody(calls: ApiCall[], method: string) {
  return calls.filter((call) => call.method === method).at(-1)?.init.body as Record<string, unknown> | undefined
}

function modelRoutes(current: object) {
  return {
    'GET /employees/{employee_id}/work-time-model': current,
    'GET /employees/{employee_id}/work-time-model/history': [],
    'PUT /employees/{employee_id}/work-time-model': model,
  }
}

describe('Abgegoltene Überstunden: Texte', () => {
  it('nennt die Grenze in der Beschreibung einer Fassung', () => {
    expect(describeVersion(fields as unknown as ModelSource)).toBe('40 h/Woche an Mo, Di, Mi, Do, Fr (8 h/Tag), abgegolten bis 10 h/Monat')
    expect(describeVersion({ ...fields, settled_overtime_minutes: 450 } as unknown as ModelSource)).toMatch(/abgegolten bis 7,5 h\/Monat$/)
    expect(describeVersion({ ...fields, settled_overtime_minutes: null } as unknown as ModelSource)).not.toMatch(/abgegolten/)
  })
})

describe('Abgegoltene Überstunden am Mitarbeiter', () => {
  it('speichert die Grenze in Stunden', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(modelRoutes(withoutLimit))
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    const input = await screen.findByLabelText('Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)')
    expect(input).toHaveValue('')
    await userEvent.type(input, '7,5')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')).toMatchObject({ settled_overtime_hours: 7.5 }))
  })

  it('schickt ohne Grenze null', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(modelRoutes(withoutLimit))
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await screen.findByLabelText('Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')).toMatchObject({ settled_overtime_hours: null }))
  })

  it('übernimmt die bisherige Grenze und zeigt sie im gültigen Modell', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(modelRoutes(model))
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText('Mit dem Gehalt abgegolten: bis 10 Std. Überstunden je Monat')).toBeInTheDocument()
    expect(screen.getByLabelText('Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)')).toHaveValue('10')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')).toMatchObject({ settled_overtime_hours: 10 }))
  })

  it('sperrt ungültige Werte', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(modelRoutes(withoutLimit))
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    const input = await screen.findByLabelText('Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)')
    const save = screen.getByRole('button', { name: 'Speichern' })
    for (const value of ['101', '-1', 'viel']) {
      await userEvent.clear(input)
      await userEvent.type(input, value)
      expect(save).toBeDisabled()
    }
    await userEvent.clear(input)
    await userEvent.type(input, '100')
    expect(save).toBeEnabled()
  })

  it('blendet das Feld bei „Nach Aufwand“ aus und schickt null', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(modelRoutes(model))
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await screen.findByLabelText('Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)')
    await userEvent.click(screen.getByRole('button', { name: 'Nach Aufwand (Aushilfe)' }))
    expect(screen.queryByLabelText('Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')).toMatchObject({ on_demand: true, settled_overtime_hours: null }))
  })

  it('gilt auch beim mehrwöchigen Modell', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(modelRoutes(withoutLimit))
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await userEvent.click(await screen.findByRole('button', { name: 'Mehrwöchig (Turnus)' }))
    await userEvent.type(screen.getByLabelText('Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)'), '5')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')).toMatchObject({ settled_overtime_hours: 5, rotation_start: null }))
  })
})

describe('Abgegoltene Überstunden in den Arbeitszeitmodellen', () => {
  it('legt ein Modell mit Grenze an und zeigt sie', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const profile = { ...fields, id: 4, name: 'Leitung', archived: false, valid_from: '2000-01-01', employee_count: 0, employees: [] }
    const calls = mockApi({ 'GET /work-time-profiles': [profile], 'POST /work-time-profiles': profile })
    renderWithProviders(<WorkTimeProfilesPage />)
    expect(await screen.findByText(/abgegolten bis 10 h\/Monat/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Neues Arbeitszeitmodell/ }))
    await userEvent.type(screen.getByLabelText('Name'), 'Leitung 2')
    await userEvent.type(screen.getByLabelText('Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)'), '12')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(calls.filter((call) => call.method === 'POST').at(-1)?.init.body).toMatchObject({ name: 'Leitung 2', settled_overtime_hours: 12 }),
    )
  })
})

describe('Kontoansicht', () => {
  const balance = {
    employee_id: 7,
    balance_date: '2026-10-19',
    daily_target_minutes: 480,
    daily_actual_minutes: 540,
    daily_delta_minutes: 60,
    running_balance_minutes: 120,
    adjustment_minutes: 0,
    balance_start: '2026-10-01',
    settled_limit_minutes: 600,
    settled_month_minutes: 270,
  }

  function routes(data: object) {
    return {
      'GET /employees/{employee_id}/overtime-balance': data,
      'GET /employees/{employee_id}/timesheet': [],
      'GET /employees/{employee_id}/weekly-balance': [],
      'GET /employees/{employee_id}/balance-adjustments': [],
    }
  }

  it('zeigt die abgegoltenen Stunden des Monats', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(routes(balance))
    renderWithProviders(<TimesheetTab employeeId={7} />)
    expect(await screen.findByText(/Davon abgegolten in diesem Monat: 4:30 von 10:00 Std\./)).toBeInTheDocument()
  })

  it('zeigt ohne Grenze keine Zeile', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(routes({ ...balance, settled_limit_minutes: null, settled_month_minutes: 0 }))
    renderWithProviders(<TimesheetTab employeeId={7} />)
    expect(await screen.findByText('Aktueller Kontostand')).toBeInTheDocument()
    await screen.findByText(/Konto seit/)
    expect(screen.queryByText(/Davon abgegolten/)).not.toBeInTheDocument()
  })
})
