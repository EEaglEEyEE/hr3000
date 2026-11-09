/** Arbeitszeitmodelle: in den Einstellungen anlegen und ab Stichtag ändern, am Mitarbeiter zuweisen
 *  (Reiter „Arbeitszeit“ und beim Anlegen). */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { WorkTimeProfilesPage } from '../../pages/WorkTimeProfilesPage'
import { WorkTimeModelTab } from './WorkTimeModelTab'

const fields = {
  weekly_minutes: 2400,
  daily_minutes: 480,
  weekdays: [0, 1, 2, 3, 4],
  day_minutes: [480, 480, 480, 480, 480, 0, 0],
  uneven: false,
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

const office = {
  ...fields,
  id: 4,
  name: 'Vollzeit Büro',
  archived: false,
  valid_from: '2000-01-01',
  late_tolerance_minutes: 10,
  flex_frame_mode: 'CUSTOM',
  flex_frame_start: '06:00:00',
  flex_frame_end: '20:00:00',
  employee_count: 2,
  employees: ['Erika Muster', 'Max Beispiel'],
}

function bodyOf(calls: ApiCall[], method: string, path: string) {
  return calls.filter((call) => call.method === method && call.path === path).at(-1)?.init.body as Record<string, unknown>
}

describe('Arbeitszeitmodelle in den Einstellungen', () => {
  it('zeigt Modelle mit Gleitzeit-Rahmen, Toleranz und zugewiesenen Mitarbeitern', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /work-time-profiles': [office] })
    renderWithProviders(<WorkTimeProfilesPage />)
    const card = await screen.findByRole('region', { name: 'Vollzeit Büro' })
    expect(within(card).getByText(/40 h\/Woche an Mo, Di, Mi, Do, Fr/)).toHaveTextContent(
      'Gleitzeit-Rahmen 06:00–20:00, Toleranz 10 Min.',
    )
    expect(within(card).getByText('Zugewiesen (heute oder später): Erika Muster, Max Beispiel')).toBeInTheDocument()
  })

  it('legt ein Modell mit eigenem Gleitzeit-Rahmen an (ohne Stichtag – gilt von Anfang an)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /work-time-profiles': [], 'POST /work-time-profiles': office })
    renderWithProviders(<WorkTimeProfilesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Neues Arbeitszeitmodell/ }))
    expect(screen.queryByLabelText('Gültig ab')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeDisabled() // Name fehlt
    await userEvent.type(screen.getByLabelText('Name'), 'Teilzeit 30')
    await userEvent.clear(screen.getByLabelText('Wochenstunden'))
    await userEvent.type(screen.getByLabelText('Wochenstunden'), '30')
    await userEvent.click(screen.getByRole('button', { name: 'Eigener Rahmen' }))
    await userEvent.type(screen.getByLabelText('Toleranz der Pünktlichkeitsprüfung (Minuten)'), '15')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(bodyOf(calls, 'POST', '/work-time-profiles')).toBeDefined())
    expect(bodyOf(calls, 'POST', '/work-time-profiles')).toMatchObject({
      name: 'Teilzeit 30',
      weekly_hours: 30,
      weekdays: [0, 1, 2, 3, 4],
      flex_frame_mode: 'CUSTOM',
      flex_frame_start: '07:00',
      flex_frame_end: '19:00',
      late_tolerance_minutes: 15,
    })
    expect(bodyOf(calls, 'POST', '/work-time-profiles')).not.toHaveProperty('valid_from')
  })

  it('ändert ein Modell ab Stichtag – vorbelegt mit der aktuellen Fassung', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /work-time-profiles': [office], 'PUT /work-time-profiles/{profile_id}/model': office })
    renderWithProviders(<WorkTimeProfilesPage />)
    const card = await screen.findByRole('region', { name: 'Vollzeit Büro' })
    await userEvent.click(within(card).getByRole('button', { name: 'Ändern ab Stichtag' }))
    expect(within(card).getByLabelText('Wochenstunden')).toHaveValue('40')
    expect(within(card).getByLabelText('Rahmen von')).toHaveValue('06:00')
    expect(within(card).getByLabelText('Toleranz der Pünktlichkeitsprüfung (Minuten)')).toHaveValue('10')
    await userEvent.clear(within(card).getByLabelText('Gültig ab'))
    await userEvent.type(within(card).getByLabelText('Gültig ab'), '2027-01-01')
    await userEvent.click(within(card).getByRole('button', { name: 'Kein Rahmen' }))
    await userEvent.click(within(card).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(bodyOf(calls, 'PUT', '/work-time-profiles/{profile_id}/model')).toBeDefined())
    expect(calls.find((call) => call.method === 'PUT')?.init.params?.path).toEqual({ profile_id: 4 })
    expect(bodyOf(calls, 'PUT', '/work-time-profiles/{profile_id}/model')).toMatchObject({
      valid_from: '2027-01-01',
      weekly_hours: 40,
      flex_frame_mode: 'NONE',
      flex_frame_start: null,
      late_tolerance_minutes: 10,
    })
  })
})

describe('Arbeitszeitmodell am Mitarbeiter', () => {
  it('weist ein Modell ab Stichtag zu', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...fields, employee_id: 7, configured: true, valid_from: '2026-10-01' },
      'GET /employees/{employee_id}/work-time-model/history': [],
      'GET /work-time-profiles': [office],
      'PUT /employees/{employee_id}/work-time-profile': { ...fields, employee_id: 7, configured: true, valid_from: '2026-11-01' },
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await userEvent.selectOptions(await screen.findByLabelText('Arbeitszeitmodell'), 'Vollzeit Büro')
    await userEvent.clear(screen.getByLabelText('Modell gültig ab'))
    await userEvent.type(screen.getByLabelText('Modell gültig ab'), '2026-11-01')
    await userEvent.click(screen.getByRole('button', { name: 'Modell zuweisen' }))
    await waitFor(() => expect(bodyOf(calls, 'PUT', '/employees/{employee_id}/work-time-profile')).toEqual({ profile_id: 4, valid_from: '2026-11-01' }))
    expect(await screen.findByText('Arbeitszeitmodell zugewiesen.')).toBeInTheDocument()
  })

  it('zeigt das zugewiesene Modell und seine Regeln im aktuellen Modell und im Verlauf', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const assigned = {
      ...fields,
      profile_id: 4,
      profile_name: 'Vollzeit Büro',
      flex_frame_mode: 'CUSTOM',
      flex_frame_start: '06:00:00',
      flex_frame_end: '20:00:00',
      late_tolerance_minutes: 10,
    }
    mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...assigned, employee_id: 7, configured: true, valid_from: '2026-10-01' },
      'GET /employees/{employee_id}/work-time-model/history': [{ ...assigned, id: 11, valid_from: '2026-10-01', valid_to: null }],
      'GET /work-time-profiles': [office],
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText('Arbeitszeitmodell „Vollzeit Büro“ – Änderungen am Modell gelten automatisch.')).toBeInTheDocument()
    expect(screen.getByText('Gleitzeit-Rahmen: 06:00–20:00')).toBeInTheDocument()
    expect(screen.getByText('Toleranz der Pünktlichkeitsprüfung: 10 Min.')).toBeInTheDocument()
    expect(screen.getByText(/^Modell „Vollzeit Büro“: 40 h\/Woche/)).toBeInTheDocument()
    expect(screen.getByText('Individuell eintragen ab Stichtag (statt zugewiesenem Modell)')).toBeInTheDocument()
  })

  it('zeigt die Zuweisung nicht, solange es keine Modelle gibt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...fields, employee_id: 7, configured: true, valid_from: '2026-10-01' },
      'GET /employees/{employee_id}/work-time-model/history': [],
      'GET /work-time-profiles': [],
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText('Neues Arbeitszeitmodell ab Stichtag')).toBeInTheDocument()
    expect(screen.queryByText('Arbeitszeitmodell zuweisen')).not.toBeInTheDocument()
  })
})
