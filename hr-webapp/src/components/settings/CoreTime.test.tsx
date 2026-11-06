/** Kernarbeitszeit & Gleitzeit: Einstellungen des Mandanten und Abweichung je Fassung des
 *  Arbeitszeitmodells. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EmployeeFormDialog } from '../employees/EmployeeFormDialog'
import { settings } from '../../test/fixtures'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { WorkTimeModelTab } from '../workTimeModel/WorkTimeModelTab'
import { CoreTimeCard, OpenDayChecksCard } from './DefaultsSettingsCard'

function settingsRoutes(initial = settings()) {
  let current = { ...initial }
  return {
    'GET /settings': () => current,
    'PATCH /settings': (init: ApiInit) => {
      current = { ...current, ...(init.body as object) }
      return current
    },
  }
}

function lastPatch(calls: ApiCall[]) {
  const patches = calls.filter((call) => call.method === 'PATCH')
  return patches.at(-1)?.init.body as Record<string, unknown> | undefined
}

describe('Einstellungen: Kernarbeitszeit & Gleitzeit', () => {
  it('speichert Kernzeit, Pünktlichkeitsprüfung, Toleranz und Rahmen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(settingsRoutes())
    renderWithProviders(<CoreTimeCard settings={settings()} />)

    await userEvent.type(screen.getByLabelText('Kernzeit von'), '09:00')
    await userEvent.type(screen.getByLabelText('Kernzeit bis'), '15:00')
    await userEvent.click(screen.getAllByRole('button', { name: 'Übernehmen' })[0])
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ core_time_start: '09:00', core_time_end: '15:00' }))

    await userEvent.click(screen.getByRole('checkbox', { name: /Zu spät gekommen/ }))
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ disabled_day_flags: ['LATE_ARRIVAL'] }))

    const tolerance = screen.getByLabelText('Toleranz in Minuten')
    await userEvent.clear(tolerance)
    await userEvent.type(tolerance, '10')
    await userEvent.click(screen.getAllByRole('button', { name: 'Übernehmen' })[1])
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ late_tolerance_minutes: 10 }))

    await userEvent.type(screen.getByLabelText(/Gleitzeit-Rahmen.* von/), '06:00')
    await userEvent.type(screen.getByLabelText(/Gleitzeit-Rahmen.* bis/), '20:00')
    await userEvent.click(screen.getAllByRole('button', { name: 'Übernehmen' })[2])
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ flex_frame_start: '06:00', flex_frame_end: '20:00' }))
  })

  it('übernimmt erst, wenn Beginn und Ende gesetzt sind', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(settingsRoutes())
    renderWithProviders(<CoreTimeCard settings={settings()} />)
    await userEvent.type(screen.getByLabelText('Kernzeit von'), '09:00')
    expect(screen.getAllByRole('button', { name: 'Übernehmen' })[0]).toBeDisabled()
  })

  it('zeigt gespeicherte Zeiten und kann sie entfernen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const current = settings({ core_time_start: '09:00:00', core_time_end: '15:00:00', flex_frame_start: '06:00:00', flex_frame_end: '20:00:00' })
    const calls = mockApi(settingsRoutes(current))
    renderWithProviders(<CoreTimeCard settings={current} />)
    expect(screen.getByLabelText('Kernzeit von')).toHaveValue('09:00')
    await userEvent.click(screen.getByRole('button', { name: 'Keine Kernzeit' }))
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ clear_core_time: true }))
    await userEvent.click(screen.getByRole('button', { name: 'Kein Rahmen' }))
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ clear_flex_frame: true }))
  })

  it('zeigt Fehlermeldungen des Servers (z. B. Kernzeit außerhalb des Rahmens)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'PATCH /settings': new ApiFailure(400, 'CORE_TIME_OUTSIDE_FRAME', 'Die Kernzeit muss innerhalb des Gleitzeit-Rahmens liegen.') })
    renderWithProviders(<CoreTimeCard settings={settings()} />)
    await userEvent.type(screen.getByLabelText('Kernzeit von'), '05:00')
    await userEvent.type(screen.getByLabelText('Kernzeit bis'), '15:00')
    await userEvent.click(screen.getAllByRole('button', { name: 'Übernehmen' })[0])
    expect(await screen.findByText('Die Kernzeit muss innerhalb des Gleitzeit-Rahmens liegen.')).toBeInTheDocument()
  })

  it('Kernzeit je Wochentag: freitags kürzer, Wochenende ohne', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const current = settings({ core_time_start: '09:00:00', core_time_end: '15:00:00' })
    const calls = mockApi(settingsRoutes(current))
    const { unmount } = renderWithProviders(<CoreTimeCard settings={current} />)
    await userEvent.click(screen.getByRole('checkbox', { name: /Kernzeit je Wochentag unterschiedlich/ }))
    // vorbelegt: Mo–Fr mit der Kernzeit, Sa/So ohne
    expect(screen.getByLabelText('Mo von')).toHaveValue('09:00')
    expect(screen.getByRole('checkbox', { name: 'Sa Kernzeit' })).not.toBeChecked()
    const fridayEnd = screen.getByLabelText('Fr bis')
    await userEvent.clear(fridayEnd)
    await userEvent.type(fridayEnd, '12:00')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Mi Kernzeit' }))
    await userEvent.click(screen.getByRole('button', { name: 'Kernzeiten übernehmen' }))
    await waitFor(() => expect(lastPatch(calls)).toHaveProperty('core_time_days'))
    const days = lastPatch(calls)!.core_time_days as unknown[]
    expect(days[2]).toBeNull()
    expect(days[4]).toEqual({ start: '09:00', end: '12:00' })
    expect(days[5]).toBeNull()
    unmount()

    // gespeichert: wieder einheitlich schaltet per null zurück
    const saved = settings({ ...current, core_time_days: days as never })
    renderWithProviders(<CoreTimeCard settings={saved} />)
    expect(screen.getByLabelText('Fr bis')).toHaveValue('12:00')
    await userEvent.click(screen.getByRole('checkbox', { name: /Kernzeit je Wochentag unterschiedlich/ }))
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ core_time_days: null }))
  })

  it('die Pünktlichkeits-Hinweise stehen nur bei der Kernarbeitszeit, nicht bei den Regeln', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(settingsRoutes())
    const { unmount } = renderWithProviders(<CoreTimeCard settings={settings({ disabled_day_flags: ['EARLY_LEAVE'] })} />)
    expect(screen.getByRole('checkbox', { name: /Zu spät gekommen/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Zu früh gegangen/ })).not.toBeChecked()
    await userEvent.click(screen.getByRole('checkbox', { name: /Gleitzeit-Rahmenzeit/ }))
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ disabled_day_flags: ['EARLY_LEAVE', 'OUTSIDE_FLEX_FRAME'] }))
    unmount()
    renderWithProviders(<OpenDayChecksCard settings={settings()} />)
    expect(screen.queryByRole('checkbox', { name: /Zu spät gekommen/ })).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Außerplanmäßig gestempelt/ })).toBeInTheDocument()
  })
})

describe('Mitarbeiter: Kernzeit im Arbeitszeitmodell', () => {
  const LOCATIONS = [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }] as never
  const model = {
    employee_id: 7,
    configured: true,
    valid_from: '2026-11-01',
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
  }

  function routes() {
    return {
      'GET /employees/{employee_id}/work-time-model': model,
      'GET /employees/{employee_id}/work-time-model/history': [{ ...model, id: 4, valid_to: null }],
      'GET /shift-templates': [],
      'PUT /employees/{employee_id}/work-time-model': model,
    }
  }

  function lastPut(calls: ApiCall[]) {
    return calls.filter((call) => call.method === 'PUT').at(-1)?.init.body as Record<string, unknown>
  }

  async function renderModel() {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes())
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await screen.findByText('40 Std.')  // geladen und Formular vorbelegt
    return calls
  }

  it('sendet "wie in den Einstellungen" als Standard', async () => {
    const calls = await renderModel()
    expect(screen.getByText('Kernarbeitszeit: wie in den Einstellungen')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastPut(calls)).toMatchObject({ core_time_mode: 'TENANT', weekly_hours: 40 }))
    expect(lastPut(calls)).not.toHaveProperty('core_time_start')
  })

  it('sendet eine eigene Kernzeit mit Uhrzeiten', async () => {
    const calls = await renderModel()
    await userEvent.selectOptions(screen.getByLabelText('Kernarbeitszeit / Pünktlichkeit'), 'CUSTOM')
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Eigene Kernzeit von'), '10:00')
    await userEvent.type(screen.getByLabelText('Eigene Kernzeit bis'), '14:00')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(lastPut(calls)).toMatchObject({ core_time_mode: 'CUSTOM', core_time_start: '10:00', core_time_end: '14:00' }),
    )
  })

  it('sendet eine eigene Kernzeit je Wochentag', async () => {
    const calls = await renderModel()
    await userEvent.selectOptions(screen.getByLabelText('Kernarbeitszeit / Pünktlichkeit'), 'CUSTOM')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Je Wochentag unterschiedlich' }))
    expect(screen.queryByLabelText('Eigene Kernzeit von')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Di Kernzeit' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastPut(calls)).toMatchObject({ core_time_mode: 'CUSTOM' }))
    const body = lastPut(calls)
    expect(body).not.toHaveProperty('core_time_start')
    const days = body.core_time_days as unknown[]
    expect(days).toHaveLength(7)
    expect(days[0]).toEqual({ start: '09:00', end: '15:00' })
    expect(days[1]).toBeNull()
  })

  it('blendet die Uhrzeiten bei "Keine Prüfung" aus und zeigt die Kernzeit im Verlauf', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      ...routes(),
      'GET /employees/{employee_id}/work-time-model/history': [
        { ...model, id: 4, valid_to: null, core_time_mode: 'CUSTOM', core_time_start: '10:00:00', core_time_end: '14:00:00' },
      ],
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText(/eigene Kernzeit 10:00–14:00/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Kernarbeitszeit / Pünktlichkeit'), 'NONE')
    expect(screen.queryByLabelText('Eigene Kernzeit von')).not.toBeInTheDocument()
  })

  it('der Mitarbeiter-Dialog fragt keine Kernzeit mehr ab', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true },
      'GET /teams': [],
      'POST /employees': (init: ApiInit) => ({ id: 9, ...(init.body as object) }),
    })
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    expect(screen.queryByLabelText('Kernarbeitszeit / Pünktlichkeit')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Vorname'), 'Paula')
    await userEvent.type(screen.getByLabelText('Nachname'), 'Pünktlich')
    await userEvent.type(screen.getByLabelText(/Personalnummer/), 'P1')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')?.init.body).not.toHaveProperty('core_time_mode')
  })
})
