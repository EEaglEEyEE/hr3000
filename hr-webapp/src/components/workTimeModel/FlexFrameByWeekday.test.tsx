/** Gleitzeit-Rahmen je Wochentag – im Arbeitszeitmodell und individuell am Mitarbeiter. */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { WorkTimeProfilesPage } from '../../pages/WorkTimeProfilesPage'
import { describeDayWindows } from '../coreTime/CoreTimeDaysEditor'
import { DEFAULT_FLEX_FRAME, flexFrameFromApi, flexFramePayload, flexFrameText, flexFrameValid } from './FlexFrameFields'
import { describeVersion, type ModelSource } from './modelText'
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
  flex_frame_days: null,
  late_tolerance_minutes: null,
  profile_id: null,
  profile_name: null,
}

const LONG = { start: '07:00:00', end: '19:00:00' }
const API_DAYS = [LONG, LONG, null, LONG, { start: '07:00:00', end: '14:00:00' }, null, null]
const perDay = { ...fields, flex_frame_mode: 'CUSTOM', flex_frame_days: API_DAYS }

function bodyOf(calls: ApiCall[], method: string, path: string) {
  return calls.filter((call) => call.method === method && call.path === path).at(-1)?.init.body as Record<string, unknown>
}

function setTime(label: string, value: string, container: HTMLElement = document.body) {
  fireEvent.change(within(container).getByLabelText(label), { target: { value } })
}

describe('Hilfen für den Gleitzeit-Rahmen', () => {
  it('fasst gleiche aufeinanderfolgende Tage zusammen', () => {
    const long = { start: '07:00', end: '19:00' }
    expect(describeDayWindows([long, long, long, long, { start: '07:00', end: '14:00' }, null, null], 'keiner')).toBe(
      'Mo–Do 07:00–19:00, Fr 07:00–14:00, Sa–So keiner',
    )
    expect(describeDayWindows([null, long, null, null, null, null, long], 'ohne')).toBe(
      'Mo ohne, Di 07:00–19:00, Mi–Sa ohne, So 07:00–19:00',
    )
  })

  it('beschreibt den Rahmen je nach Art', () => {
    expect(flexFrameText({ flex_frame_mode: 'TENANT' })).toBe('')
    expect(flexFrameText({})).toBe('')
    expect(flexFrameText({ flex_frame_mode: 'NONE' })).toBe('keiner')
    expect(flexFrameText({ flex_frame_mode: 'CUSTOM', flex_frame_start: '06:00:00', flex_frame_end: '20:00:00' })).toBe('06:00–20:00')
    expect(flexFrameText({ flex_frame_mode: 'CUSTOM', flex_frame_days: API_DAYS })).toBe(
      'je Wochentag (Mo–Di 07:00–19:00, Mi keiner, Do 07:00–19:00, Fr 07:00–14:00, Sa–So keiner)',
    )
    expect(flexFrameText({ flex_frame_mode: 'CUSTOM' })).toBe('') // unvollständig
  })

  it('liest die API, prüft und baut die Anfrage', () => {
    expect(flexFrameFromApi({})).toEqual(DEFAULT_FLEX_FRAME)
    const loaded = flexFrameFromApi(perDay)
    expect(loaded.mode).toBe('CUSTOM')
    expect(loaded.days?.[4]).toEqual({ start: '07:00', end: '14:00' })
    expect(flexFramePayload(loaded)).toEqual({ flex_frame_mode: 'CUSTOM', flex_frame_start: null, flex_frame_end: null, flex_frame_days: loaded.days })
    const single = { ...DEFAULT_FLEX_FRAME, mode: 'CUSTOM' as const }
    expect(flexFramePayload(single)).toEqual({ flex_frame_mode: 'CUSTOM', flex_frame_start: '07:00', flex_frame_end: '19:00', flex_frame_days: null })
    expect(flexFramePayload({ ...loaded, mode: 'NONE' })).toEqual({ flex_frame_mode: 'NONE', flex_frame_start: null, flex_frame_end: null, flex_frame_days: null })
    expect(flexFrameValid(single)).toBe(true)
    expect(flexFrameValid({ ...single, start: '19:00', end: '07:00' })).toBe(false)
    expect(flexFrameValid({ ...single, end: '' })).toBe(false)
    expect(flexFrameValid({ ...loaded, days: [{ start: '12:00', end: '08:00' }, null, null, null, null, null, null] })).toBe(false)
    expect(flexFrameValid({ ...single, mode: 'TENANT', start: '' })).toBe(true) // ohne eigenen Rahmen egal
  })

  it('nennt den Rahmen je Wochentag im Verlauf', () => {
    expect(describeVersion(perDay as ModelSource)).toContain('Gleitzeit-Rahmen je Wochentag (Mo–Di 07:00–19:00, Mi keiner')
  })
})

describe('Arbeitszeitmodell mit Rahmen je Wochentag', () => {
  it('legt ein Modell mit Rahmen je Wochentag an – freitags kürzer, mittwochs keiner', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /work-time-profiles': [], 'POST /work-time-profiles': { ...perDay, id: 5, name: 'Fr kurz' } })
    renderWithProviders(<WorkTimeProfilesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Neues Arbeitszeitmodell/ }))
    await userEvent.type(screen.getByLabelText('Name'), 'Fr kurz')
    await userEvent.click(screen.getByRole('button', { name: 'Eigener Rahmen' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Rahmen je Wochentag unterschiedlich' }))
    // Vorschlag: Mo–Fr der bisherige Rahmen, Wochenende ohne
    expect(screen.getByLabelText('Rahmen Mo von')).toHaveValue('07:00')
    expect(screen.queryByLabelText('Rahmen Sa von')).not.toBeInTheDocument()
    setTime('Rahmen Fr bis', '14:00')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Mi Rahmen' }))
    expect(screen.getAllByText('kein Rahmen')).toHaveLength(3) // Mi, Sa, So

    // ungültiger Tag sperrt das Speichern
    setTime('Rahmen Mo von', '20:00')
    expect(screen.getByText('Der Beginn muss jeweils vor dem Ende liegen.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeDisabled()
    setTime('Rahmen Mo von', '07:00')

    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(bodyOf(calls, 'POST', '/work-time-profiles')).toBeDefined())
    const long = { start: '07:00', end: '19:00' }
    expect(bodyOf(calls, 'POST', '/work-time-profiles')).toMatchObject({
      name: 'Fr kurz',
      flex_frame_mode: 'CUSTOM',
      flex_frame_start: null,
      flex_frame_end: null,
      flex_frame_days: [long, long, null, long, { start: '07:00', end: '14:00' }, null, null],
    })
  })

  it('zeigt den Rahmen je Wochentag in der Übersicht und lädt ihn zum Ändern', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const profile = { ...perDay, id: 5, name: 'Fr kurz', archived: false, valid_from: '2000-01-01', employee_count: 0, employees: [] }
    const calls = mockApi({ 'GET /work-time-profiles': [profile], 'PUT /work-time-profiles/{profile_id}/model': profile })
    renderWithProviders(<WorkTimeProfilesPage />)
    const card = await screen.findByRole('region', { name: 'Fr kurz' })
    expect(within(card).getByText(/Gleitzeit-Rahmen je Wochentag \(Mo–Di 07:00–19:00, Mi keiner, Do 07:00–19:00, Fr 07:00–14:00, Sa–So keiner\)/)).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'Ändern ab Stichtag' }))
    expect(within(card).getByRole('checkbox', { name: 'Rahmen je Wochentag unterschiedlich' })).toBeChecked()
    expect(within(card).getByLabelText('Rahmen Fr bis')).toHaveValue('14:00')
    // zurück auf einen Rahmen für alle Tage
    await userEvent.click(within(card).getByRole('checkbox', { name: 'Rahmen je Wochentag unterschiedlich' }))
    expect(within(card).getByLabelText('Rahmen von')).toHaveValue('07:00')
    await userEvent.click(within(card).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(bodyOf(calls, 'PUT', '/work-time-profiles/{profile_id}/model')).toBeDefined())
    expect(bodyOf(calls, 'PUT', '/work-time-profiles/{profile_id}/model')).toMatchObject({
      flex_frame_mode: 'CUSTOM',
      flex_frame_start: '07:00',
      flex_frame_end: '19:00',
      flex_frame_days: null,
    })
  })
})

describe('Gleitzeit-Rahmen am Mitarbeiter', () => {
  it('lässt den Rahmen individuell festlegen – ohne eigene Toleranz', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...fields, employee_id: 7, configured: true, valid_from: '2026-10-01' },
      'GET /employees/{employee_id}/work-time-model/history': [],
      'GET /work-time-profiles': [],
      'PUT /employees/{employee_id}/work-time-model': { ...perDay, employee_id: 7, configured: true, valid_from: '2026-11-01' },
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByRole('button', { name: 'Wie Einstellungen' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByLabelText('Toleranz der Pünktlichkeitsprüfung (Minuten)')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Eigener Rahmen' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Rahmen je Wochentag unterschiedlich' }))
    setTime('Rahmen Fr bis', '14:00')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(bodyOf(calls, 'PUT', '/employees/{employee_id}/work-time-model')).toBeDefined())
    const body = bodyOf(calls, 'PUT', '/employees/{employee_id}/work-time-model')
    expect(body).toMatchObject({ flex_frame_mode: 'CUSTOM', flex_frame_start: null })
    expect((body.flex_frame_days as unknown[])[4]).toEqual({ start: '07:00', end: '14:00' })
    expect(body).not.toHaveProperty('late_tolerance_minutes')
  })

  it('sendet ohne Änderung „wie Einstellungen“ und zeigt einen eigenen Rahmen je Wochentag an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...perDay, employee_id: 7, configured: true, valid_from: '2026-10-01' },
      'GET /employees/{employee_id}/work-time-model/history': [{ ...perDay, id: 3, valid_from: '2026-10-01', valid_to: null }],
      'GET /work-time-profiles': [],
      'PUT /employees/{employee_id}/work-time-model': { ...fields, employee_id: 7, configured: true, valid_from: '2026-11-01' },
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText(/^Gleitzeit-Rahmen: je Wochentag \(Mo–Di 07:00–19:00/)).toBeInTheDocument()
    // Formular übernimmt den Rahmen der aktuellen Fassung
    expect(screen.getByRole('checkbox', { name: 'Rahmen je Wochentag unterschiedlich' })).toBeChecked()
    expect(screen.getByLabelText('Rahmen Fr bis')).toHaveValue('14:00')
    await userEvent.click(screen.getByRole('button', { name: 'Wie Einstellungen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(bodyOf(calls, 'PUT', '/employees/{employee_id}/work-time-model')).toBeDefined())
    expect(bodyOf(calls, 'PUT', '/employees/{employee_id}/work-time-model')).toMatchObject({
      flex_frame_mode: 'TENANT',
      flex_frame_start: null,
      flex_frame_end: null,
      flex_frame_days: null,
    })
  })
})
