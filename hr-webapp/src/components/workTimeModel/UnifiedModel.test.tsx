/** Arbeitszeitmodell und Schicht an einer Stelle: Modell-Art in zwei Fragen, Schichtvorlage nur für
 *  die Uhrzeiten, ältere Standard-Schichten, Schichtplan-Reiter und Kalender ohne Vorlage. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { EmployeeShiftRow } from '../shiftplanning/EmployeeShiftRow'
import { ShiftPlanTab } from '../shiftplanning/ShiftPlanTab'
import { WorkTimeModelTab } from './WorkTimeModelTab'

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

const early = {
  id: 3,
  name: 'Früh',
  start_time: '06:00:00',
  end_time: '14:30:00',
  break_mode: 'FIXED',
  fixed_break_start: '10:00:00',
  fixed_break_end: '10:30:00',
  min_break_minutes: null,
  min_break_after_minutes: 0,
  target_minutes: 480,
  target_period: 'DAILY',
  location_id: null,
  archived: false,
}

function lastPut(calls: ApiCall[]) {
  return calls.filter((call) => call.method === 'PUT').at(-1)?.init.body as Record<string, unknown>
}

describe('Arbeitszeitmodell mit Schichtvorlage', () => {
  it('wählt eine Schichtvorlage nur für die Uhrzeiten und übernimmt deren Pause', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': model,
      'GET /employees/{employee_id}/work-time-model/history': [],
      'GET /shift-templates': [early],
      'GET /features': { shift_planning_enabled: true },
      'PUT /employees/{employee_id}/work-time-model': model,
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    await screen.findByText('40 Std.')
    expect(screen.getByRole('button', { name: 'Wie Pausenregeln' })).toBeInTheDocument()

    await userEvent.selectOptions(await screen.findByLabelText('Schichtvorlage (Uhrzeiten, optional)'), 'Früh (06:00–14:30)')
    expect(screen.getByRole('button', { name: 'Wie Schichtvorlage' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Es gilt die Pause der Schichtvorlage \(10:00–10:30\)/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastPut(calls)).toMatchObject({ weekly_hours: 40, weekdays: [0, 1, 2, 3, 4], shift_template_id: 3 }))
    expect(lastPut(calls)).not.toHaveProperty('break_start')

    // ohne Vorlage wieder "keine festen Uhrzeiten"
    await userEvent.selectOptions(screen.getByLabelText('Schichtvorlage (Uhrzeiten, optional)'), 'Keine festen Uhrzeiten')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.filter((call) => call.method === 'PUT')).toHaveLength(2))
    expect(lastPut(calls)).toMatchObject({ shift_template_id: null })
  })

  it('fragt Arbeitstage und Soll getrennt ab; Stunden je Wochentag übernehmen die Wochenstunden', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...model, configured: false },
      'GET /employees/{employee_id}/work-time-model/history': [],
      'GET /shift-templates': [],
      'PUT /employees/{employee_id}/work-time-model': model,
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByRole('button', { name: 'Feste Arbeitstage' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.clear(screen.getByLabelText('Wochenstunden'))
    await userEvent.type(screen.getByLabelText('Wochenstunden'), '20')
    await userEvent.click(screen.getByRole('checkbox', { name: /Stunden je Wochentag unterschiedlich/ }))
    expect(screen.getByLabelText('Stunden Mo')).toHaveValue('4')
    await userEvent.clear(screen.getByLabelText('Stunden Fr'))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastPut(calls)).toMatchObject({ daily_hours: [4, 4, 4, 4, 0, 0, 0] }))

    // flexibel: keine Soll-Frage, kein Wochentag
    await userEvent.click(screen.getByRole('button', { name: 'Flexibel ohne feste Tage' }))
    expect(screen.queryByRole('button', { name: 'Monatsstunden (fest)' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastPut(calls)).toMatchObject({ flexible: true, weekly_hours: 20 }))
  })

  it('zeigt eine ältere Standard-Schicht mit Soll aus der Vorlage und lässt jede Fassung bearbeiten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const legacy = {
      ...model,
      target_from_template: true,
      shift_template_id: 3,
      shift_template_name: 'Früh',
      shift_start: '06:00:00',
      shift_end: '14:30:00',
      break_start: '10:00:00',
      break_end: '10:30:00',
      break_from_template: true,
    }
    mockApi({
      'GET /employees/{employee_id}/work-time-model': legacy,
      'GET /employees/{employee_id}/work-time-model/history': [{ ...legacy, id: 4, valid_to: null }],
      'GET /shift-templates': [early],
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText(/Das Soll kommt bisher aus der Schichtvorlage „Früh“/)).toBeInTheDocument()
    expect(screen.getByText('Pause: 10:00–10:30 (laut Schichtvorlage)')).toBeInTheDocument()
    expect(screen.getByText(/Schicht „Früh“ 06:00–14:30/, { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Bearbeiten' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Wie Schichtvorlage' })).toHaveAttribute('aria-pressed', 'true'))
  })
})

describe('Schichtplan-Reiter', () => {
  it('zeigt die regelmäßige Arbeitszeit aus dem Modell statt einer eigenen Standard-Schicht', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...model, shift_template_id: 3, shift_template_name: 'Früh', shift_start: '06:00:00', shift_end: '14:30:00' },
      'GET /employees/{employee_id}/shift-plan-entries': [],
      'GET /shift-templates': [early],
    })
    renderWithProviders(<ShiftPlanTab employeeId={7} />)
    expect(await screen.findByText('Regelmäßige Arbeitszeit')).toBeInTheDocument()
    expect(await screen.findByText('Uhrzeiten: Schicht „Früh“ 06:00–14:30')).toBeInTheDocument()
    expect(screen.queryByText('Neue Standard-Schicht')).not.toBeInTheDocument()
  })
})

describe('Kalender ohne Schichtvorlage', () => {
  it('zeigt das Tagessoll des Modells bzw. "flexibel"', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees/{employee_id}/effective-shifts': [
        { date: '2026-11-02', is_workday: true, plan_exists: true, from_entry: false, shift_template_id: null, target_minutes: 450, flexible: false, on_demand: false },
        { date: '2026-11-03', is_workday: true, plan_exists: true, from_entry: false, shift_template_id: null, target_minutes: null, flexible: true, on_demand: false },
        { date: '2026-11-04', is_workday: true, plan_exists: false, from_entry: true, shift_template_id: 3, target_minutes: null, flexible: false, on_demand: true },
      ],
    })
    const employee = { id: 7, first_name: 'Vera', last_name: 'Vertrag' } as never
    renderWithProviders(
      <table>
        <tbody>
          <EmployeeShiftRow
            employee={employee}
            weekDates={['2026-11-02', '2026-11-03', '2026-11-04']}
            templateById={new Map([[3, early as never]])}
            readOnly
            onError={() => undefined}
          />
        </tbody>
      </table>,
    )
    const row = await screen.findByRole('row')
    expect(await within(row).findByText('7,5 h')).toBeInTheDocument()
    expect(within(row).getByText('flexibel')).toBeInTheDocument()
    // nach Aufwand mit geplanter Schicht: Uhrzeiten sichtbar
    expect(within(row).getByText('Früh')).toBeInTheDocument()
    expect(within(row).getByText('06:00–14:30')).toBeInTheDocument()
  })
})
