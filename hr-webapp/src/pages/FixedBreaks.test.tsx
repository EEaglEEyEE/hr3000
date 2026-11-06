/** Pausenregeln an einer Stelle: Staffel (inkl. betrieblicher Mindestwerte), feste Pausenzeiten,
 *  Berechnung mit „gilt ab“, automatisches Stempeln; eigene Pause im Arbeitszeitmodell. */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { settings } from '../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../test/utils'
import { WorkTimeModelTab } from '../components/workTimeModel/WorkTimeModelTab'
import { BreakRulesPage } from './BreakRulesPage'

const legal = [
  { id: 1, kind: 'LEGAL', min_work_minutes: 360, deduct_minutes: 30, start_time: null, end_time: null, valid_from: '2000-01-01', valid_to: null },
  { id: 2, kind: 'LEGAL', min_work_minutes: 540, deduct_minutes: 45, start_time: null, end_time: null, valid_from: '2000-01-01', valid_to: null },
]
const lunch = {
  id: 3,
  kind: 'FIXED_WINDOW',
  min_work_minutes: 0,
  deduct_minutes: 30,
  start_time: '12:00:00',
  end_time: '12:30:00',
  valid_from: '2026-11-01',
  valid_to: null,
}

function lastBody(calls: ApiCall[], method: string) {
  return calls.filter((call) => call.method === method).at(-1)?.init.body as Record<string, unknown> | undefined
}

function routes(rules: unknown[] = [...legal, lunch]) {
  let current = settings()
  return {
    'GET /break-rules': rules,
    'POST /break-rules': lunch,
    'GET /settings': () => current,
    'PATCH /settings': (init: ApiInit) => {
      current = { ...current, ...(init.body as object) }
      return current
    },
  }
}

describe('Pausenregeln', () => {
  it('zeigt Staffel und feste Pausenzeiten getrennt und legt eine Pausenzeit an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes())
    renderWithProviders(<BreakRulesPage />)

    expect(await screen.findByText('Gesetzliche Pausenstaffel')).toBeInTheDocument()
    expect(await screen.findByLabelText('Pause von', { selector: 'td input' })).toHaveValue('12:00')
    const form = screen.getByRole('button', { name: /Pausenzeit hinzufügen/ }).closest('form')!
    await userEvent.clear(within(form).getByLabelText('Pause von'))
    await userEvent.type(within(form).getByLabelText('Pause von'), '09:00')
    await userEvent.clear(within(form).getByLabelText('Pause bis'))
    await userEvent.type(within(form).getByLabelText('Pause bis'), '09:15')
    await userEvent.click(within(form).getByRole('button', { name: /Pausenzeit hinzufügen/ }))
    await waitFor(() =>
      expect(lastBody(calls, 'POST')).toMatchObject({ kind: 'FIXED_WINDOW', start_time: '09:00', end_time: '09:15' }),
    )
  })

  it('legt eine strengere Staffelzeile des Betriebs an (statt „feste Minuten“)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes(legal))
    renderWithProviders(<BreakRulesPage />)
    await screen.findByText('Gesetzliche Pausenstaffel')
    await userEvent.clear(screen.getByLabelText('Ab Arbeitsminuten', { selector: '#min_work_minutes' }))
    await userEvent.type(screen.getByLabelText('Ab Arbeitsminuten', { selector: '#min_work_minutes' }), '240')
    await userEvent.click(screen.getByRole('button', { name: /Regel hinzufügen/ }))
    await waitFor(() => expect(lastBody(calls, 'POST')).toMatchObject({ kind: 'LEGAL', min_work_minutes: 240, deduct_minutes: 30 }))
  })

  it('schaltet die Berechnung ab einem Datum und das automatische Stempeln', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes())
    renderWithProviders(<BreakRulesPage />)
    const precise = await screen.findByRole('checkbox', { name: /genau nach § 4 ArbZG/ })
    fireEvent.change(screen.getByLabelText('Pausen genau nach § 4 ArbZG rechnen gilt ab'), { target: { value: '2026-12-01' } })
    await userEvent.click(precise)
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ break_precise_from: '2026-12-01' }))
    expect(await screen.findByText(/gilt ab 1\.12\.2026/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox', { name: /genau nach § 4 ArbZG/ }))
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ clear_break_precise: true }))

    await userEvent.click(screen.getByRole('checkbox', { name: /Pausen automatisch stempeln/ }))
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ default_auto_break: false }))
    await userEvent.click(screen.getByRole('checkbox', { name: /Gesetzliche Mindestpause nicht unterschreiten/ }))
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ legal_break_minimum: false }))
  })
})

describe('Arbeitszeitmodell: eigene Pause', () => {
  const model = {
    employee_id: 7,
    configured: true,
    is_work_time_model: true,
    template_name: 'Arbeitszeitmodell 40 h/Woche, Pause 12:00–12:30',
    weekly_minutes: 2400,
    daily_minutes: 480,
    weekdays: [0, 1, 2, 3, 4],
    day_minutes: null,
    monthly_minutes: null,
    break_minutes: null,
    break_after_minutes: 0,
    break_start: '12:00:00',
    break_end: '12:30:00',
    valid_from: '2026-11-01',
  }

  it('zeigt die Pause und speichert feste Minuten ab einer Arbeitszeit', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': model,
      'GET /employees/{employee_id}/work-time-model/history': [
        { ...model, id: 4, valid_to: null, uneven: false, flexible: false, on_demand: false, monthly_cap_minutes: null },
      ],
      'PUT /employees/{employee_id}/work-time-model': model,
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)

    expect(await screen.findByText('Pause: 12:00–12:30')).toBeInTheDocument()
    expect(screen.getByText(/40 h\/Woche an Mo, Di, Mi, Do, Fr \(8 h\/Tag\), Pause 12:00–12:30/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Feste Uhrzeit' })).toHaveAttribute('aria-pressed', 'true'))

    await userEvent.click(screen.getByRole('button', { name: 'Feste Minuten' }))
    await userEvent.clear(screen.getByLabelText('Pausenminuten'))
    await userEvent.type(screen.getByLabelText('Pausenminuten'), '45')
    await userEvent.type(screen.getByLabelText('Pause ab Stunden'), '6')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PUT')).toMatchObject({ weekly_hours: 40, break_minutes: 45, break_after_hours: 6 }))
    expect(lastBody(calls, 'PUT')).not.toHaveProperty('break_start')

    // zurück auf die Pausenregeln: keine eigene Pause mehr im Payload
    await userEvent.click(screen.getByRole('button', { name: 'Wie Pausenregeln' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(2))
    expect(lastBody(calls, 'PUT')).not.toHaveProperty('break_minutes')
  })
})
