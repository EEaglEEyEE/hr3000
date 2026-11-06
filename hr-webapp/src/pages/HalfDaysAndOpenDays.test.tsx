/** Halbe Abwesenheitstage im Formular und "Erledigt" in "Zu klären". */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AbsenceFormDialog } from '../components/absences/AbsenceFormDialog'
import { dayCellStyle, dayCellTooltip } from '../lib/dayCellStyle'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { openDay } from '../test/fixtures'
import { OpenDaysPage } from './OpenDaysPage'

const TYPES = [
  { id: 1, name: 'Urlaub', color: '#10b981', category: 'VACATION', requires_approval: false, employee_can_request: true, certificate_from_day: null, active: true, sort_order: 1 },
  { id: 3, name: 'Sonderurlaub', color: '#64748b', category: 'SPECIAL_LEAVE', requires_approval: false, employee_can_request: false, certificate_from_day: null, active: true, sort_order: 3 },
]

describe('Abwesenheit: halber Tag und Stunden', () => {
  function renderForm(post: unknown = (init: ApiInit) => ({ id: 9, ...(init.body as object) }), types: unknown[] = TYPES) {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /absence-types': types, 'POST /absences': post })
    const onOpenChange = vi.fn()
    renderWithProviders(<AbsenceFormDialog open onOpenChange={onOpenChange} employeeId={5} />)
    return { calls, onOpenChange }
  }

  async function setDates(from: string, to: string) {
    const fromInput = screen.getByLabelText('Von')
    const toInput = screen.getByLabelText('Bis')
    await userEvent.clear(fromInput)
    await userEvent.type(fromInput, from)
    await userEvent.clear(toInput)
    await userEvent.type(toInput, to)
  }

  it('sendet einen halben Urlaubstag', async () => {
    const { calls, onOpenChange } = renderForm()
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Urlaub'))
    await setDates('2026-12-24', '2026-12-24')
    await userEvent.selectOptions(screen.getByLabelText('Umfang'), 'HALF')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    const post = calls.find((call) => call.method === 'POST')
    expect(post?.init.body).toMatchObject({ employee_id: 5, absence_type_id: 1, date_from: '2026-12-24', date_to: '2026-12-24', half_day: true })
  })

  it('bietet "halber Tag" nur für einen einzelnen Tag an und sendet sonst ganze Tage', async () => {
    const { calls } = renderForm()
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Urlaub'))
    await setDates('2026-12-24', '2026-12-24')
    await userEvent.selectOptions(screen.getByLabelText('Umfang'), 'HALF')
    await setDates('2026-12-21', '2026-12-24')
    expect(screen.queryByLabelText('Umfang')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')?.init.body).toMatchObject({ half_day: false })
  })

  const HOMEOFFICE = [{ ...TYPES[1], id: 7, name: 'Homeoffice' }]

  it('sendet eine genaue Stundenzahl (z. B. 1,5 Std. Homeoffice)', async () => {
    const { calls, onOpenChange } = renderForm(undefined, HOMEOFFICE)
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Homeoffice'))
    await setDates('2026-10-05', '2026-10-05')
    await userEvent.selectOptions(screen.getByLabelText('Umfang'), 'HOURS')
    const save = screen.getByRole('button', { name: 'Speichern' })
    expect(save).toBeDisabled() // ohne Stunden
    await userEvent.type(screen.getByLabelText('Stunden'), '0')
    expect(save).toBeDisabled()
    await userEvent.clear(screen.getByLabelText('Stunden'))
    await userEvent.type(screen.getByLabelText('Stunden'), '1,5')
    await userEvent.click(save)
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(calls.find((call) => call.method === 'POST')?.init.body).toMatchObject({
      absence_type_id: 7,
      date_from: '2026-10-05',
      half_day: false,
      duration_minutes: 90,
    })
  })

  it('bietet bei Urlaub keine Stunden an (Urlaub zählt in Tagen)', async () => {
    renderForm()
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Urlaub'))
    const options = Array.from((screen.getByLabelText('Umfang') as HTMLSelectElement).options, (o) => o.value)
    expect(options).toEqual(['FULL', 'HALF'])
  })

  it('zeigt beim Bearbeiten die Stunden und kann auf ganzen Tag zurückstellen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /absence-types': HOMEOFFICE, 'PATCH /absences/{absence_id}': (init: ApiInit) => ({ id: 4, ...(init.body as object) }) })
    const absence = {
      id: 4, employee_id: 5, type: 'SPECIAL_LEAVE', absence_type_id: 7, date_from: '2026-10-05', date_to: '2026-10-05',
      half_day: false, duration_minutes: 180, created_by: null, created_by_employee_id: null, note: null,
      approval_status: 'APPROVED', decided_by: null, decided_by_employee_id: null, decided_at: null,
    } as never
    renderWithProviders(<AbsenceFormDialog open onOpenChange={vi.fn()} employeeId={5} absence={absence} />)
    expect(await screen.findByLabelText('Stunden')).toHaveValue('3')
    await userEvent.selectOptions(screen.getByLabelText('Umfang'), 'FULL')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true))
    expect(calls.find((call) => call.method === 'PATCH')?.init.body).toMatchObject({ half_day: false, clear_duration: true })
  })

  it('zeigt den Konflikt mit einem bereits belegten Tag an', async () => {
    const { onOpenChange } = renderForm(new ApiFailure(409, 'ABSENCE_OVERLAP', 'An diesem Tag sind bereits zwei halbe Tage eingetragen.'))
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Urlaub'))
    await setDates('2026-12-24', '2026-12-24')
    await userEvent.selectOptions(screen.getByLabelText('Umfang'), 'HALF')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('An diesem Tag sind bereits zwei halbe Tage eingetragen.')).toBeInTheDocument()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })
})

describe('Kalenderzellen für halbe Tage', () => {
  const types = new Map(TYPES.map((t) => [t.id, t])) as Parameters<typeof dayCellStyle>[1]
  const base = { work_date: '2026-12-24', target_minutes: 480, is_birthday: false, exceeds_max_daily_minutes: false, flags: [], reviewed: false }

  it('zeigt "½ Urlaub" und die Arbeitszeit, mit Strich in der Urlaubsfarbe', () => {
    const day = { ...base, status: 'COMPLETE' as const, actual_minutes: 480, absence_type: 'VACATION' as const, absence_type_id: 1, absence_label: '½ Urlaub' }
    expect(dayCellTooltip(day, types)).toBe('½ Urlaub · Ist +8:00')
    expect(dayCellStyle(day, types)).toEqual({ boxShadow: 'inset 0 -3px 0 #10b981' })
  })

  it('zeigt zwei halbe Tage als gemeinsame Abwesenheit', () => {
    const day = { ...base, status: 'ABSENCE' as const, actual_minutes: 480, absence_type: 'SPECIAL_LEAVE' as const, absence_type_id: 3, absence_label: '½ Sonderurlaub + ½ Urlaub' }
    expect(dayCellTooltip(day, types)).toBe('½ Sonderurlaub + ½ Urlaub')
  })
})

describe('Zu klären: Erledigt', () => {
  function routes(days = [openDay(2, '2026-10-19'), { ...openDay(3, '2026-10-20'), status: 'COMPLETE', flags: ['UNPLANNED_WORK'] }]) {
    let current = [...days]
    return {
      'GET /locations': [],
      'GET /punch-correction-requests': [],
      'GET /timesheet/monthly-caps': [],
      'GET /timesheet/open-days': () => current,
      'PUT /employees/{employee_id}/day-reviews/{work_date}': (init: ApiInit) => {
        current = current.filter((d) => !(d.employee_id === init.params?.path?.employee_id && d.work_date === init.params?.path?.work_date))
        return undefined
      },
      'DELETE /employees/{employee_id}/day-reviews/{work_date}': () => {
        current = [...days]
        return undefined
      },
    }
  }

  function row(date: string) {
    return screen.getByText(date).closest('tr') as HTMLElement
  }

  it('markiert einen Sonderfall ohne Rückfrage als erledigt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const confirm = vi.spyOn(window, 'confirm')
    const calls = mockApi(routes())
    renderWithProviders(<OpenDaysPage />)
    await screen.findByText('20.10.2026')
    await userEvent.click(within(row('20.10.2026')).getByRole('button', { name: 'Erledigt' }))
    await waitFor(() => expect(screen.queryByText('20.10.2026')).not.toBeInTheDocument())
    expect(confirm).not.toHaveBeenCalled()
    expect(calls.find((call) => call.method === 'PUT')?.init.params?.path).toEqual({ employee_id: 3, work_date: '2026-10-20' })
  })

  it('fragt bei fehlender Stempelung nach und tut bei "Abbrechen" nichts', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const calls = mockApi(routes())
    renderWithProviders(<OpenDaysPage />)
    await screen.findByText('19.10.2026')
    await userEvent.click(within(row('19.10.2026')).getByRole('button', { name: 'Erledigt' }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('ohne die Stempelung zu korrigieren'))
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)
    expect(screen.getByText('19.10.2026')).toBeInTheDocument()
  })

  it('markiert nach Bestätigung und lässt sich rückgängig machen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const calls = mockApi(routes())
    renderWithProviders(<OpenDaysPage />)
    await screen.findByText('19.10.2026')
    await userEvent.click(within(row('19.10.2026')).getByRole('button', { name: 'Erledigt' }))
    await waitFor(() => expect(screen.queryByText('19.10.2026')).not.toBeInTheDocument())
    expect(screen.getByText(/als erledigt markiert/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Rückgängig' }))
    expect(await screen.findByText('19.10.2026')).toBeInTheDocument()
    expect(calls.find((call) => call.method === 'DELETE')?.init.params?.path).toEqual({ employee_id: 2, work_date: '2026-10-19' })
    expect(screen.queryByText(/als erledigt markiert/)).not.toBeInTheDocument()
  })

  it('Teamleader sehen weder "Erledigt" noch "Korrigieren" (entscheidet und korrigiert nur HR)', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi(routes())
    renderWithProviders(<OpenDaysPage />)
    await screen.findByText('19.10.2026')
    expect(screen.queryByRole('button', { name: 'Erledigt' })).not.toBeInTheDocument()
    expect(screen.queryByText('Korrigieren →')).not.toBeInTheDocument()
  })
})
