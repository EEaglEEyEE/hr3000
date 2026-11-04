/** Kernarbeitszeit & Gleitzeit: Einstellungen des Mandanten und Abweichung je Mitarbeiter. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EmployeeFormDialog } from '../employees/EmployeeFormDialog'
import { settings } from '../../test/fixtures'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { CoreTimeCard, RulesCard } from './DefaultsSettingsCard'

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

    await userEvent.click(screen.getByRole('checkbox', { name: /Pünktlichkeit prüfen/ }))
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ punctuality_check: true }))

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

  it('die neuen Sonderfälle lassen sich unter "Regeln" einzeln abschalten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(settingsRoutes())
    renderWithProviders(<RulesCard settings={settings()} />)
    const late = screen.getByRole('checkbox', { name: /Zu spät gekommen/ })
    expect(late).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Zu früh gegangen/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Gleitzeit-Rahmenzeit/ })).toBeChecked()
    await userEvent.click(late)
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ disabled_day_flags: ['LATE_ARRIVAL'] }))
  })
})

describe('Mitarbeiter: eigene Kernzeit', () => {
  const LOCATIONS = [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }] as never

  function routes() {
    return {
      'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true },
      'GET /teams': [],
      'POST /employees': (init: ApiInit) => ({ id: 9, ...(init.body as object) }),
    }
  }

  async function fillBasics() {
    await userEvent.type(screen.getByLabelText('Vorname'), 'Paula')
    await userEvent.type(screen.getByLabelText('Nachname'), 'Pünktlich')
    await userEvent.type(screen.getByLabelText(/Personalnummer/), 'P1')
  }

  it('sendet "wie in den Einstellungen" als Standard', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes())
    const onOpenChange = vi.fn()
    renderWithProviders(<EmployeeFormDialog open onOpenChange={onOpenChange} locations={LOCATIONS} />)
    await fillBasics()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')?.init.body).toMatchObject({ core_time_mode: 'TENANT' })
    expect(calls.find((call) => call.method === 'POST')?.init.body).not.toHaveProperty('core_time_start')
  })

  it('sendet eine eigene Kernzeit mit Uhrzeiten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes())
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    await userEvent.selectOptions(screen.getByLabelText('Kernarbeitszeit / Pünktlichkeit'), 'CUSTOM')
    await userEvent.type(screen.getByLabelText('Eigene Kernzeit von'), '10:00')
    await userEvent.type(screen.getByLabelText('Eigene Kernzeit bis'), '14:00')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')?.init.body).toMatchObject({
      core_time_mode: 'CUSTOM',
      core_time_start: '10:00',
      core_time_end: '14:00',
    })
  })

  it('blendet die Uhrzeiten bei "Keine Prüfung" aus', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(routes())
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await userEvent.selectOptions(screen.getByLabelText('Kernarbeitszeit / Pünktlichkeit'), 'NONE')
    expect(screen.queryByLabelText('Eigene Kernzeit von')).not.toBeInTheDocument()
  })
})
