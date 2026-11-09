/** Mehrere feste Pausenzeiten im Arbeitszeitmodell (z. B. Frühstück und Mittag). */
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { WorkTimeProfilesPage } from '../../pages/WorkTimeProfilesPage'
import { breakWindowsValid, MAX_BREAK_WINDOWS, nextBreakWindow } from './BreakWindowsEditor'
import { breakLabel } from './modelText'
import { WorkTimeModelTab } from './WorkTimeModelTab'

const fields = {
  weekly_minutes: 2400, daily_minutes: 480, weekdays: [0, 1, 2, 3, 4], day_minutes: [480, 480, 480, 480, 480, 0, 0],
  uneven: false, flexible: false, on_demand: false, monthly_cap_minutes: null, monthly_minutes: null, target_from_template: false,
  break_minutes: null, break_after_minutes: 0, break_start: null, break_end: null, break_windows: null, break_from_template: false,
  shift_template_id: null, shift_template_name: null, shift_start: null, shift_end: null,
  core_time_mode: 'TENANT', core_time_start: null, core_time_end: null, core_time_days: null,
  flex_frame_mode: 'TENANT', flex_frame_start: null, flex_frame_end: null, flex_frame_days: null,
  late_tolerance_minutes: null, profile_id: null, profile_name: null,
}
const twoBreaks = {
  ...fields,
  break_start: '09:00:00',
  break_end: '09:15:00',
  break_windows: [{ start: '09:00:00', end: '09:15:00' }, { start: '12:00:00', end: '12:30:00' }],
}

function lastBody(calls: ApiCall[], method: string, path: string) {
  return calls.filter((call) => call.method === method && call.path === path).at(-1)?.init.body as Record<string, unknown> | undefined
}

describe('Hilfen für feste Pausenzeiten', () => {
  it('prüft Vollständigkeit, Reihenfolge und Überschneidung', () => {
    expect(breakWindowsValid([{ start: '12:00', end: '12:30' }, { start: '09:00', end: '09:15' }])).toBe(true)
    expect(breakWindowsValid([{ start: '09:00', end: '09:15' }, { start: '09:15', end: '09:30' }])).toBe(true) // direkt hintereinander
    expect(breakWindowsValid([{ start: '09:00', end: '10:00' }, { start: '09:30', end: '10:30' }])).toBe(false)
    expect(breakWindowsValid([{ start: '12:30', end: '12:00' }])).toBe(false)
    expect(breakWindowsValid([{ start: '', end: '12:00' }])).toBe(false)
    expect(breakWindowsValid([])).toBe(false)
    expect(breakWindowsValid(Array.from({ length: MAX_BREAK_WINDOWS + 1 }, (_, i) => ({ start: `0${i}:00`, end: `0${i}:10` })))).toBe(false)
  })

  it('schlägt die nächste Pausenzeit eine Stunde nach der letzten vor', () => {
    expect(nextBreakWindow([{ start: '09:00', end: '09:15' }])).toEqual({ start: '10:15', end: '10:30' })
    expect(nextBreakWindow([])).toEqual({ start: '09:00', end: '09:15' })
    expect(nextBreakWindow([{ start: '22:30', end: '23:30' }])).toEqual({ start: '09:00', end: '09:15' })
    expect(nextBreakWindow([{ start: '21:00', end: '22:50' }])).toEqual({ start: '23:50', end: '23:59' })
  })

  it('beschreibt mehrere Pausenzeiten', () => {
    expect(breakLabel(twoBreaks)).toBe(', Pause 09:00–09:15, 12:00–12:30')
    const single = { break_start: '12:00:00', break_end: '12:30:00', break_windows: [{ start: '12:00:00', end: '12:30:00' }] }
    expect(breakLabel(single)).toBe(', Pause 12:00–12:30')
  })
})

describe('Mehrere Pausenzeiten im Formular', () => {
  it('legt ein Modell mit Frühstücks- und Mittagspause an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /work-time-profiles': [], 'POST /work-time-profiles': { ...twoBreaks, id: 9, name: 'Werk' } })
    renderWithProviders(<WorkTimeProfilesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Neues Arbeitszeitmodell/ }))
    await userEvent.type(screen.getByLabelText('Name'), 'Werk')
    await userEvent.click(screen.getByRole('button', { name: 'Feste Uhrzeit' }))
    fireEvent.change(screen.getByLabelText('Pause von'), { target: { value: '09:00' } })
    fireEvent.change(screen.getByLabelText('Pause bis'), { target: { value: '09:15' } })
    await userEvent.click(screen.getByRole('button', { name: 'Weitere Pausenzeit' }))
    fireEvent.change(screen.getByLabelText('Pause 2 von'), { target: { value: '12:00' } })
    fireEvent.change(screen.getByLabelText('Pause 2 bis'), { target: { value: '12:30' } })

    // Überschneidung sperrt das Speichern
    fireEvent.change(screen.getByLabelText('Pause 2 von'), { target: { value: '09:10' } })
    expect(screen.getByText(/dürfen sich nicht überschneiden/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Pause 2 von'), { target: { value: '12:00' } })

    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'POST', '/work-time-profiles')).toBeDefined())
    const body = lastBody(calls, 'POST', '/work-time-profiles')!
    expect(body.break_windows).toEqual([{ start: '09:00', end: '09:15' }, { start: '12:00', end: '12:30' }])
    expect(body).not.toHaveProperty('break_start')
  })

  it('sendet eine einzelne Pausenzeit wie bisher und begrenzt auf vier', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...fields, employee_id: 7, configured: true, valid_from: '2026-10-01' },
      'GET /employees/{employee_id}/work-time-model/history': [],
      'GET /work-time-profiles': [],
      'PUT /employees/{employee_id}/work-time-model': { ...fields, employee_id: 7, configured: true, valid_from: '2026-10-01' },
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await userEvent.click(await screen.findByRole('button', { name: 'Feste Uhrzeit' }))
    for (let i = 1; i < 4; i++) await userEvent.click(screen.getByRole('button', { name: 'Weitere Pausenzeit' }))
    expect(screen.queryByRole('button', { name: 'Weitere Pausenzeit' })).not.toBeInTheDocument() // höchstens vier
    for (let i = 4; i > 1; i--) await userEvent.click(screen.getByRole('button', { name: `Pausenzeit ${i} entfernen` }))
    expect(screen.queryByRole('button', { name: /entfernen/ })).not.toBeInTheDocument() // die letzte bleibt
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT', '/employees/{employee_id}/work-time-model')).toBeDefined())
    const body = lastBody(calls, 'PUT', '/employees/{employee_id}/work-time-model')!
    expect(body).toMatchObject({ break_start: '12:00', break_end: '12:30' })
    expect(body).not.toHaveProperty('break_windows')
  })

  it('zeigt und lädt gespeicherte Pausenzeiten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...twoBreaks, employee_id: 7, configured: true, valid_from: '2026-10-01' },
      'GET /employees/{employee_id}/work-time-model/history': [{ ...twoBreaks, id: 4, valid_from: '2026-10-01', valid_to: null }],
      'GET /work-time-profiles': [],
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText('Pause: 09:00–09:15, 12:00–12:30')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Feste Uhrzeit' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Pause von')).toHaveValue('09:00')
    expect(screen.getByLabelText('Pause 2 bis')).toHaveValue('12:30')
  })
})
