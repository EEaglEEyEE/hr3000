/** Mehrwöchiges Arbeitszeitmodell (Turnus über 2–4 Wochen): Eingabe am Mitarbeiter und in den
 *  Arbeitszeitmodellen, Anzeige des gültigen Modells und des Verlaufs, Text- und Rechenhilfen. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { LeaveEntitlement } from '../../api/queries/leaveEntitlements'
import { WorkTimeProfilesPage } from '../../pages/WorkTimeProfilesPage'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { LeaveEntitlementCard } from '../absences/LeaveEntitlementCard'
import { describeVersion, rotationText, rotationWeekIndex, type ModelSource } from './modelText'
import { WorkTimeModelTab } from './WorkTimeModelTab'

const ROTATION = [
  [480, 480, 480, 0, 0, 0, 0],
  [0, 0, 0, 480, 480, 0, 0],
]

const fields = {
  weekly_minutes: 1200,
  daily_minutes: null,
  weekdays: [0, 1, 2, 3, 4],
  day_minutes: null,
  uneven: false,
  rotation_minutes: ROTATION,
  rotation_start: '2026-09-28',
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

const rotationModel = { ...fields, employee_id: 7, configured: true, is_work_time_model: true, valid_from: '2026-10-01' }
const evenModel = {
  ...rotationModel,
  configured: false,
  weekly_minutes: 2400,
  daily_minutes: 480,
  day_minutes: [480, 480, 480, 480, 480, 0, 0],
  rotation_minutes: null,
  rotation_start: null,
}

function lastBody(calls: ApiCall[], method: string) {
  return calls.filter((call) => call.method === method).at(-1)?.init.body as Record<string, unknown> | undefined
}

describe('Turnus: Rechen- und Texthilfen', () => {
  it('bestimmt die Turnus-Woche eines Tages (auch vor dem Start und über Jahreswechsel)', () => {
    expect(rotationWeekIndex('2026-09-28', 2, new Date(2026, 8, 28))).toBe(0)
    expect(rotationWeekIndex('2026-09-28', 2, new Date(2026, 9, 4))).toBe(0) // Sonntag der Woche 1
    expect(rotationWeekIndex('2026-09-28', 2, new Date(2026, 9, 5))).toBe(1)
    expect(rotationWeekIndex('2026-09-28', 2, new Date(2026, 9, 12))).toBe(0)
    expect(rotationWeekIndex('2026-09-28', 2, new Date(2026, 8, 21))).toBe(1) // eine Woche davor
    expect(rotationWeekIndex('2026-09-28', 3, new Date(2026, 9, 12))).toBe(2)
    expect(rotationWeekIndex('2026-09-28', 4, new Date(2026, 9, 26))).toBe(0)
    expect(rotationWeekIndex('2026-10-01', 2, new Date(2026, 8, 28))).toBe(0) // Start mitten in der Woche
    // über die Umstellung auf Winterzeit (25.10.2026) und den Jahreswechsel
    expect(rotationWeekIndex('2026-10-19', 2, new Date(2026, 9, 26))).toBe(1)
    expect(rotationWeekIndex('2026-12-28', 2, new Date(2027, 0, 4))).toBe(1)
  })

  it('beschreibt einen Turnus als Text, auch mit freier Woche', () => {
    expect(rotationText(ROTATION)).toBe('Woche 1: Mo 8 h, Di 8 h, Mi 8 h; Woche 2: Do 8 h, Fr 8 h')
    expect(rotationText([[450, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]])).toBe('Woche 1: Mo 7,5 h; Woche 2: frei')
  })

  it('beschreibt eine Fassung mit Turnus', () => {
    expect(describeVersion(fields as unknown as ModelSource)).toBe(
      'im Schnitt 20 h/Woche, Turnus über 2 Wochen (Woche 1: Mo 8 h, Di 8 h, Mi 8 h; Woche 2: Do 8 h, Fr 8 h), Woche 1 ab 28.9.2026',
    )
    expect(describeVersion({ ...fields, rotation_start: null } as unknown as ModelSource)).not.toMatch(/Woche 1 ab/)
    expect(describeVersion({ ...fields, rotation_minutes: [] } as unknown as ModelSource)).toBe('20 h/Woche an Mo, Di, Mi, Do, Fr')
  })
})

describe('Turnus am Mitarbeiter', () => {
  it('speichert einen zweiwöchigen Turnus mit Startpunkt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': evenModel,
      'GET /employees/{employee_id}/work-time-model/history': [],
      'PUT /employees/{employee_id}/work-time-model': rotationModel,
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await userEvent.click(await screen.findByRole('button', { name: 'Mehrwöchig (Turnus)' }))
    expect(screen.getByLabelText('Wochen im Turnus')).toHaveValue('2')
    // Vorbelegt: zwei Wochen Mo–Fr 8 Std.
    expect(screen.getByText(/im Schnitt 40 h pro Woche an im Schnitt 5 Arbeitstagen/)).toBeInTheDocument()

    for (const day of ['Do', 'Fr']) await userEvent.clear(screen.getByLabelText(`Woche 1 Stunden ${day}`))
    for (const day of ['Mo', 'Di', 'Mi']) await userEvent.clear(screen.getByLabelText(`Woche 2 Stunden ${day}`))
    expect(screen.getByText(/im Schnitt 20 h pro Woche an im Schnitt 2,5 Arbeitstagen/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Turnus beginnt am (optional)'), '2026-09-30')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(lastBody(calls, 'PUT')).toMatchObject({
        rotation_weeks: [
          [8, 8, 8, 0, 0, 0, 0],
          [0, 0, 0, 8, 8, 0, 0],
        ],
        rotation_start: '2026-09-30',
        flexible: false,
        on_demand: false,
      }),
    )
    const body = lastBody(calls, 'PUT')!
    expect(body).not.toHaveProperty('weekly_hours')
    expect(body).not.toHaveProperty('daily_hours')
  })

  it('schickt ohne Startpunkt null (Woche 1 = Woche des „Gültig ab“)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': evenModel,
      'GET /employees/{employee_id}/work-time-model/history': [],
      'PUT /employees/{employee_id}/work-time-model': rotationModel,
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await userEvent.click(await screen.findByRole('button', { name: 'Mehrwöchig (Turnus)' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')).toMatchObject({ rotation_start: null }))
  })

  it('erweitert auf drei und vier Wochen und kürzt wieder', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': evenModel,
      'GET /employees/{employee_id}/work-time-model/history': [],
      'PUT /employees/{employee_id}/work-time-model': rotationModel,
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await userEvent.click(await screen.findByRole('button', { name: 'Mehrwöchig (Turnus)' }))
    await userEvent.clear(screen.getByLabelText('Woche 2 Stunden Fr'))
    await userEvent.selectOptions(screen.getByLabelText('Wochen im Turnus'), '4')
    // neue Wochen übernehmen die Stunden der letzten Woche
    expect(screen.getByLabelText('Woche 4 Stunden Fr')).toHaveValue('')
    expect(screen.getByLabelText('Woche 3 Stunden Mo')).toHaveValue('8')
    await userEvent.selectOptions(screen.getByLabelText('Wochen im Turnus'), '3')
    expect(screen.queryByLabelText('Woche 4 Stunden Mo')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')?.rotation_weeks).toHaveLength(3))
  })

  it('sperrt Speichern bei ungültigen Stunden', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees/{employee_id}/work-time-model': evenModel,
      'GET /employees/{employee_id}/work-time-model/history': [],
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await userEvent.click(await screen.findByRole('button', { name: 'Mehrwöchig (Turnus)' }))
    const save = screen.getByRole('button', { name: 'Speichern' })
    const monday = screen.getByLabelText('Woche 1 Stunden Mo')
    await userEvent.clear(monday)
    await userEvent.type(monday, '11') // mehr als 10 Std. am Tag
    expect(save).toBeDisabled()
    await userEvent.clear(monday)
    await userEvent.type(monday, 'abc')
    expect(save).toBeDisabled()
    await userEvent.clear(monday)
    await userEvent.type(monday, '8')
    expect(save).toBeEnabled()
    // alle Tage leer: kein Soll -> gesperrt
    for (const week of [1, 2]) {
      for (const day of ['Mo', 'Di', 'Mi', 'Do', 'Fr']) await userEvent.clear(screen.getByLabelText(`Woche ${week} Stunden ${day}`))
    }
    expect(save).toBeDisabled()
  })

  it('zeigt die Fehlermeldung des Backends', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees/{employee_id}/work-time-model': evenModel,
      'GET /employees/{employee_id}/work-time-model/history': [],
      'PUT /employees/{employee_id}/work-time-model': new ApiFailure(409, 'PERIOD_LOCKED', 'Der Monat ist abgeschlossen.'),
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await userEvent.click(await screen.findByRole('button', { name: 'Mehrwöchig (Turnus)' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Der Monat ist abgeschlossen.')).toBeInTheDocument()
  })

  it('zeigt das gültige Turnus-Modell, belegt das Formular vor und listet den Verlauf', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': rotationModel,
      'GET /employees/{employee_id}/work-time-model/history': [{ ...fields, id: 3, valid_from: '2026-10-01', valid_to: null }],
      'PUT /employees/{employee_id}/work-time-model': rotationModel,
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText('Mehrwöchig (2 Wochen)')).toBeInTheDocument()
    expect(screen.getByText('pro Woche im Schnitt')).toBeInTheDocument()
    expect(screen.getByText(/Woche 1 beginnt am 28\.9\.2026/)).toBeInTheDocument()
    expect(screen.getByText(/Turnus über 2 Wochen \(Woche 1: Mo 8 h, Di 8 h, Mi 8 h; Woche 2: Do 8 h, Fr 8 h\)/)).toBeInTheDocument()

    // Formular: Turnus und Startpunkt übernommen (der Rhythmus läuft weiter)
    expect(screen.getByRole('button', { name: 'Mehrwöchig (Turnus)' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Woche 2 Stunden Do')).toHaveValue('8')
    expect(screen.getByLabelText('Woche 2 Stunden Mo')).toHaveValue('')
    expect(screen.getByLabelText('Turnus beginnt am (optional)')).toHaveValue('2026-09-28')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')).toMatchObject({ rotation_weeks: [[8, 8, 8, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0]], rotation_start: '2026-09-28' }))
  })

  it('markiert die laufende Turnus-Woche', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const today = new Date()
    const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - ((today.getDay() + 6) % 7))
    const pad = (value: number) => String(value).padStart(2, '0')
    const start = `${monday.getFullYear()}-${pad(monday.getMonth() + 1)}-${pad(monday.getDate())}`
    mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...rotationModel, rotation_start: start },
      'GET /employees/{employee_id}/work-time-model/history': [],
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit={false} />)
    expect(await screen.findByText('Woche 1 (jetzt)')).toBeInTheDocument()
    expect(screen.getByText('Woche 2')).toBeInTheDocument()
  })
})

describe('Turnus in den Arbeitszeitmodellen', () => {
  const profile = {
    ...fields,
    id: 5,
    name: 'Wechselwoche',
    archived: false,
    valid_from: '2000-01-01',
    employee_count: 1,
    employees: ['Erika Muster'],
  }

  it('zeigt ein Modell mit Turnus', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /work-time-profiles': [profile] })
    renderWithProviders(<WorkTimeProfilesPage />)
    const card = await screen.findByRole('region', { name: 'Wechselwoche' })
    expect(within(card).getByText(/im Schnitt 20 h\/Woche, Turnus über 2 Wochen/)).toBeInTheDocument()
  })

  it('legt ein Modell mit dreiwöchigem Turnus an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /work-time-profiles': [], 'POST /work-time-profiles': profile })
    renderWithProviders(<WorkTimeProfilesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Neues Arbeitszeitmodell/ }))
    await userEvent.type(screen.getByLabelText('Name'), 'Drei Wochen')
    await userEvent.click(screen.getByRole('button', { name: 'Mehrwöchig (Turnus)' }))
    await userEvent.selectOptions(screen.getByLabelText('Wochen im Turnus'), '3')
    await userEvent.clear(screen.getByLabelText('Woche 3 Stunden Mo'))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => {
      const body = calls.filter((call) => call.method === 'POST' && call.path === '/work-time-profiles').at(-1)?.init.body as Record<string, unknown>
      expect(body).toMatchObject({ name: 'Drei Wochen', rotation_start: null })
      expect(body.rotation_weeks).toEqual([
        [8, 8, 8, 8, 8, 0, 0],
        [8, 8, 8, 8, 8, 0, 0],
        [0, 8, 8, 8, 8, 0, 0],
      ])
    })
  })
})

describe('Urlaubsanspruch beim Turnus', () => {
  function entitlement(workdays: number): LeaveEntitlement {
    return {
      employee_id: 7,
      year: new Date().getFullYear(),
      entitled_days: 15,
      carried_over_days: 0,
      used_days: 0,
      remaining_days: 15,
      carried_over_auto: false,
      expired_days: 0,
      expiring_days: 0,
      expiry_date: null,
      suggested_entitled_days: 15,
      entitled_manual: false,
      annual_vacation_days: 30,
      workdays_per_week: workdays,
      adjustment_days: 0,
    }
  }

  it('zeigt durchschnittliche Arbeitstage mit Komma', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /employees/{employee_id}/leave-entitlement': entitlement(2.5),
      'GET /employees/{employee_id}/leave-adjustments': [],
    })
    renderWithProviders(<LeaveEntitlementCard employeeId={7} />)
    expect(await screen.findByText(/\(2,5 pro Woche im Schnitt\)/)).toBeInTheDocument()
  })

  it('zeigt ganze Arbeitstage wie bisher', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /employees/{employee_id}/leave-entitlement': entitlement(4),
      'GET /employees/{employee_id}/leave-adjustments': [],
    })
    renderWithProviders(<LeaveEntitlementCard employeeId={7} />)
    expect(await screen.findByText(/\(4 pro Woche\)/)).toBeInTheDocument()
  })
})
