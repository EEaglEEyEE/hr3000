/** Mitarbeiter ohne Zeiterfassung: keine Zeit-Reiter, Kennzeichnung, neutraler Kalender, keine Zeiten in
 * Startseite, Anwesenheitsübersicht, Lohnbuchhaltung und Monatsabschluss. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TimesheetDay } from '../api/queries/timesheets'
import { Dashboard } from '../components/dashboard/Dashboard'
import { PeriodClosuresSelfTab } from '../components/periods/PeriodClosuresSelfTab'
import { CalendarTab } from '../components/timesheet/CalendarTab'
import { dayCellTooltip, DAY_CELL_LEGEND_WITHOUT_TIME_TRACKING } from '../lib/dayCellStyle'
import { formatHoursMinutes } from '../lib/format'
import { dashboard, dashboardMe, employee } from '../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../test/utils'
import { AttendanceOverviewPage } from './AttendanceOverviewPage'
import { EmployeeDetailPage } from './EmployeeDetailPage'
import { EmployeesPage } from './EmployeesPage'
import { PayrollAccountingPage } from './PayrollAccountingPage'
import { PeriodClosuresPage } from './PeriodClosuresPage'
import { SelfServicePage } from './SelfServicePage'

afterEach(() => vi.restoreAllMocks())

function day(overrides: Partial<TimesheetDay> = {}): TimesheetDay {
  return {
    work_date: '2026-11-02',
    target_minutes: null,
    actual_minutes: null,
    status: 'OPEN_MISSING_PUNCH',
    absence_type: null,
    absence_type_id: null,
    is_birthday: false,
    exceeds_max_daily_minutes: false,
    flags: [],
    reviewed: false,
    ...overrides,
  }
}

function paths(calls: ApiCall[]) {
  return calls.map((call) => `${call.method} ${call.path}`)
}

// ---------------------------------------------------------------- Detailseite

function detailApi(initial: ReturnType<typeof employee>) {
  let current = initial
  const calls = mockApi({
    'GET /employees/{employee_id}': () => current,
    'GET /locations': [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }],
    'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true },
    'GET /departments': [],
    'GET /employees': [],
    'GET /employees/{employee_id}/timesheet': [],
    'GET /employees/{employee_id}/weekly-balance': [],
    'PATCH /employees/{employee_id}': (init: ApiInit) => {
      current = { ...current, ...(init.body as object) }
      return current
    },
  })
  return calls
}

function renderDetail(route = '/employees/5') {
  return renderWithProviders(
    <Routes>
      <Route path="/employees/:employeeId" element={<EmployeeDetailPage />} />
    </Routes>,
    { route },
  )
}

describe('Detailseite ohne Zeiterfassung', () => {
  it('zeigt mit Zeiterfassung alle Zeit-Reiter und keine Kennzeichnung', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    detailApi(employee({ time_tracking: true }))
    renderDetail()
    expect(await screen.findByRole('tab', { name: 'Zeiterfassung' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Überstundenkonto' })).toBeInTheDocument()
    expect(screen.queryByText('ohne Zeiterfassung')).not.toBeInTheDocument()
    // erster Reiter ist wie bisher „Zeiterfassung“
    expect(screen.getByRole('tab', { name: 'Zeiterfassung' })).toHaveAttribute('aria-selected', 'true')
  })

  it('blendet „Zeiterfassung“ und „Überstundenkonto“ aus und kennzeichnet den Mitarbeiter', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    detailApi(employee({ time_tracking: false }))
    renderDetail()
    const calendar = await screen.findByRole('tab', { name: 'Kalender' })
    expect(screen.queryByRole('tab', { name: 'Zeiterfassung' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Überstundenkonto' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Arbeitszeit' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Abwesenheiten' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('ohne Zeiterfassung')
    // ausgewählt ist der erste vorhandene Reiter
    expect(calendar).toHaveAttribute('aria-selected', 'true')
  })

  it('öffnet trotzdem direkt die Einstellungen über ?reiter=einstellungen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    detailApi(employee({ time_tracking: false }))
    renderDetail('/employees/5?reiter=einstellungen')
    expect(await screen.findByRole('tab', { name: 'Einstellungen' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('checkbox', { name: 'Zeiterfassung' })).not.toBeChecked()
  })

  it('bleibt nach dem Ausschalten im Reiter „Einstellungen“, die Zeit-Reiter verschwinden', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = detailApi(employee({ time_tracking: true }))
    renderDetail()
    await userEvent.click(await screen.findByRole('tab', { name: 'Einstellungen' }))
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Zeiterfassung' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'Zeiterfassung' })).not.toBeInTheDocument())
    expect(calls.find((c) => c.method === 'PATCH')?.init.body).toMatchObject({ time_tracking: false })
    expect(screen.getByRole('tab', { name: 'Einstellungen' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Gespeichert.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('ohne Zeiterfassung')
  })

  it('fällt auf den ersten Reiter zurück, wenn der gewählte verschwindet', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    let tracking = true
    mockApi({
      'GET /employees/{employee_id}': () => employee({ time_tracking: tracking }),
      'GET /locations': [],
      'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true },
      'GET /employees/{employee_id}/timesheet': [],
      'GET /employees/{employee_id}/weekly-balance': [],
    })
    const { queryClient } = renderDetail()
    await userEvent.click(await screen.findByRole('tab', { name: 'Überstundenkonto' }))
    expect(screen.getByRole('tab', { name: 'Überstundenkonto' })).toHaveAttribute('aria-selected', 'true')
    tracking = false
    await queryClient.invalidateQueries({ queryKey: ['employees'] })
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'Überstundenkonto' })).not.toBeInTheDocument())
    expect(screen.getByRole('tab', { name: 'Kalender' })).toHaveAttribute('aria-selected', 'true')
  })
})

// ---------------------------------------------------------------- Kalender

describe('Kalender ohne Zeiterfassung', () => {
  function calendarApi() {
    return mockApi({
      'GET /employees/{employee_id}/timesheet': (init: ApiInit) => [
        day({ work_date: String(init.params?.query?.from) }),
      ],
      'GET /employees/{employee_id}/weekly-balance': [],
      'GET /absence-types': [],
    })
  }

  it('zeigt Arbeitstage neutral, ohne Wochenspalte Soll/Ist und ohne Stempel-Legende', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = calendarApi()
    renderWithProviders(<CalendarTab employeeId={5} timeTracking={false} />)
    expect(await screen.findByTitle('Ohne Zeiterfassung')).toBeInTheDocument()
    expect(screen.queryByTitle('Keine Stempelung')).not.toBeInTheDocument()
    expect(screen.queryByText('Woche')).not.toBeInTheDocument()
    expect(screen.queryByTitle('Soll/Ist/Saldo dieser Kalenderwoche')).not.toBeInTheDocument()
    expect(paths(calls)).not.toContain('GET /employees/{employee_id}/weekly-balance')
    expect(screen.queryByText('Keine Stempelung')).not.toBeInTheDocument()
    expect(screen.queryByText('Anwesend')).not.toBeInTheDocument()
    expect(screen.getByText('Feiertag')).toBeInTheDocument()
  })

  it('bleibt mit Zeiterfassung unverändert (Wochenspalte, „Keine Stempelung“)', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = calendarApi()
    renderWithProviders(<CalendarTab employeeId={5} />)
    expect(await screen.findByTitle('Keine Stempelung')).toBeInTheDocument()
    expect(screen.getByText('Woche')).toBeInTheDocument()
    await waitFor(() => expect(paths(calls)).toContain('GET /employees/{employee_id}/weekly-balance'))
    expect(screen.getByText('Anwesend')).toBeInTheDocument()
  })

  it('beschreibt Tage im Tooltip neutral, Abwesenheiten und Feiertage bleiben', () => {
    const off = { timeTracking: false }
    expect(dayCellTooltip(day(), undefined, off)).toBe('Ohne Zeiterfassung')
    expect(dayCellTooltip(day(), undefined, { timeTracking: true })).toBe('Keine Stempelung')
    expect(dayCellTooltip(day())).toBe('Keine Stempelung')
    expect(dayCellTooltip(day({ status: 'HOLIDAY' }), undefined, off)).toBe('Feiertag')
    expect(dayCellTooltip(day({ status: 'PLANNED_OFF' }), undefined, off)).toBe('Frei laut Schichtplan')
    expect(dayCellTooltip(day({ status: 'ABSENCE', absence_type: 'VACATION' }), undefined, off)).toBe('Urlaub')
    expect(dayCellTooltip(day({ absence_label: '½ Urlaub', absence_type_id: 3 }), undefined, off)).toBe(
      '½ Urlaub · Ohne Zeiterfassung',
    )
    expect(dayCellTooltip(undefined, undefined, off)).toBeUndefined()
  })

  it('hat eine eigene Legende ohne Stempelstatus', () => {
    const labels = DAY_CELL_LEGEND_WITHOUT_TIME_TRACKING.map((entry) => entry.label)
    expect(labels).toEqual(['Feiertag', 'Frei laut Plan', 'Ohne Zeiterfassung'])
  })
})

// ---------------------------------------------------------------- Mein Bereich

describe('Mein Bereich ohne Zeiterfassung', () => {
  function renderSelf(timeTracking: boolean) {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({
      'GET /employees/{employee_id}': employee({ time_tracking: timeTracking }),
      'GET /dashboard': dashboard({ me: dashboardMe({ time_tracking: timeTracking }) }),
    })
    renderWithProviders(<SelfServicePage />, { route: '/mein-bereich' })
  }

  it('zeigt keine Reiter „Zeiterfassung“ und „Überstundenkonto“, Monatsabschluss bleibt', async () => {
    renderSelf(false)
    expect(await screen.findByRole('tab', { name: 'Übersicht' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Zeiterfassung' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Überstundenkonto' })).not.toBeInTheDocument()
    for (const name of ['Kalender', 'Abwesenheiten', 'Monatsabschluss', 'Dokumente', 'Meine Daten']) {
      expect(screen.getByRole('tab', { name })).toBeInTheDocument()
    }
  })

  it('zeigt mit Zeiterfassung beide Reiter', async () => {
    renderSelf(true)
    expect(await screen.findByRole('tab', { name: 'Zeiterfassung' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Überstundenkonto' })).toBeInTheDocument()
  })

  it('zeigt im Monatsabschluss „–“ statt 0:00 (Monate von früher behalten ihre Werte)', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const closure = {
      id: 1, employee_id: 5, year: 2026, month: 10, status: 'SUBMITTED', target_minutes: 0, actual_minutes: 0,
      delta_minutes: 0, balance_end_minutes: 0, settled_minutes: 0, document_id: null, submitted_at: '2026-11-02T08:00:00',
      confirmed_at: null, disputed_at: null, dispute_reason: null, closed_at: null, closed_without_confirmation: false,
    }
    const earlier = { ...closure, id: 2, month: 9, status: 'CLOSED', target_minutes: 9600, actual_minutes: 9660, delta_minutes: 60 }
    mockApi({ 'GET /employees/{employee_id}/period-closures': [closure, earlier], 'GET /employees/{employee_id}/documents': [] })
    renderWithProviders(<PeriodClosuresSelfTab employeeId={5} timeTracking={false} />)
    const october = (await screen.findByText('Oktober 2026')).closest('tr')!
    expect(within(october).getAllByText('–')).toHaveLength(3)
    const september = screen.getByText('September 2026').closest('tr')!
    expect(within(september).getByText('160:00')).toBeInTheDocument()
    expect(within(september).getByText('+1:00')).toBeInTheDocument()
  })

  it('zeigt im Monatsabschluss mit Zeiterfassung 0:00', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({
      'GET /employees/{employee_id}/period-closures': [
        {
          id: 1, employee_id: 5, year: 2026, month: 10, status: 'SUBMITTED', target_minutes: 0, actual_minutes: 0,
          delta_minutes: 0, balance_end_minutes: 0, settled_minutes: 0, document_id: null, submitted_at: '2026-11-02T08:00:00',
          confirmed_at: null, disputed_at: null, dispute_reason: null, closed_at: null, closed_without_confirmation: false,
        },
      ],
      'GET /employees/{employee_id}/documents': [],
    })
    renderWithProviders(<PeriodClosuresSelfTab employeeId={5} />)
    const october = (await screen.findByText('Oktober 2026')).closest('tr')!
    expect(within(october).getAllByText('0:00')).toHaveLength(3)
  })
})

// ---------------------------------------------------------------- Startseite

describe('Startseite ohne Zeiterfassung', () => {
  async function renderMe(me: Parameters<typeof dashboardMe>[0]) {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({ 'GET /dashboard': dashboard({ me: dashboardMe(me) }) })
    renderWithProviders(<Dashboard />)
    await screen.findByText('Hallo Erika')
  }

  it('zeigt nur Resturlaub – kein Konto, kein Heute, keine Woche', async () => {
    await renderMe({
      time_tracking: false, balance_minutes: null, balance_date: null, week_actual_minutes: null, week_target_minutes: null,
    })
    expect(screen.getByText('Resturlaub 2026')).toBeInTheDocument()
    expect(screen.queryByText('Überstundenkonto')).not.toBeInTheDocument()
    expect(screen.queryByText('Heute')).not.toBeInTheDocument()
    expect(screen.queryByText('Diese Woche')).not.toBeInTheDocument()
    expect(screen.queryByText(/^Stempeln \(Home-Office/)).not.toBeInTheDocument()
  })

  it('zeigt auch bei „nach Aufwand“ keine Monatsstunden', async () => {
    await renderMe({ time_tracking: false, on_demand: true, balance_minutes: null, week_actual_minutes: null, week_target_minutes: null })
    expect(screen.queryByText('Diesen Monat')).not.toBeInTheDocument()
    expect(screen.getByText('Resturlaub 2026')).toBeInTheDocument()
  })

  it('zeigt offene Anträge weiterhin an', async () => {
    await renderMe({ time_tracking: false, balance_minutes: null, week_actual_minutes: null, week_target_minutes: null, pending_absences: 1 })
    expect(screen.getByText(/1 Abwesenheitsantrag/)).toBeInTheDocument()
  })

  it('zeigt mit Zeiterfassung alle Kacheln', async () => {
    await renderMe({ time_tracking: true })
    for (const label of ['Überstundenkonto', 'Resturlaub 2026', 'Heute', 'Diese Woche']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('stürzt bei leeren Werten trotz Zeiterfassung nicht ab', async () => {
    await renderMe({ time_tracking: true, balance_minutes: null, week_actual_minutes: null, week_target_minutes: null })
    expect(screen.getByText('Überstundenkonto')).toBeInTheDocument()
    // Konto und Woche fallen auf 0 zurück
    expect(screen.getAllByText('0:00 Std.')).toHaveLength(2)
  })
})

// ---------------------------------------------------------------- Listen und Übersichten

describe('Mitarbeiterliste', () => {
  it('kennzeichnet Mitarbeiter ohne Zeiterfassung', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees': [
        employee({ id: 1, first_name: 'Tina', last_name: 'Takt', time_tracking: true }),
        employee({ id: 2, first_name: 'Olga', last_name: 'Ohne', time_tracking: false }),
      ],
      'GET /locations': [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }],
      'GET /departments': [],
    })
    renderWithProviders(<EmployeesPage />)
    const without = (await screen.findByText('Ohne, Olga')).closest('tr')!
    expect(within(without).getByText('ohne Zeiterfassung')).toBeInTheDocument()
    const tracked = screen.getByText('Takt, Tina').closest('tr')!
    expect(within(tracked).queryByText('ohne Zeiterfassung')).not.toBeInTheDocument()
  })
})

describe('Anwesenheitsübersicht', () => {
  it('lässt Mitarbeiter ohne Zeiterfassung weg und lädt für sie keine Tage', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /employees': [
        employee({ id: 1, first_name: 'Tina', last_name: 'Takt', time_tracking: true }),
        employee({ id: 2, first_name: 'Olga', last_name: 'Ohne', time_tracking: false }),
      ],
      'GET /locations': [],
      'GET /employees/{employee_id}/timesheet': [],
      'GET /absence-types': [],
    })
    renderWithProviders(<AttendanceOverviewPage />)
    expect(await screen.findByText('Takt, Tina')).toBeInTheDocument()
    expect(screen.queryByText('Ohne, Olga')).not.toBeInTheDocument()
    await waitFor(() => expect(calls.some((c) => c.path === '/employees/{employee_id}/timesheet')).toBe(true))
    const loaded = calls.filter((c) => c.path === '/employees/{employee_id}/timesheet').map((c) => c.init.params?.path?.employee_id)
    expect(loaded).toEqual([1])
  })

  it('meldet „Keine aktiven Mitarbeiter“, wenn nur Mitarbeiter ohne Zeiterfassung da sind', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /employees': [employee({ id: 2, first_name: 'Olga', last_name: 'Ohne', time_tracking: false })],
      'GET /locations': [],
      'GET /absence-types': [],
    })
    renderWithProviders(<AttendanceOverviewPage />)
    expect(await screen.findByText('Keine aktiven Mitarbeiter gefunden.')).toBeInTheDocument()
    expect(paths(calls)).not.toContain('GET /employees/{employee_id}/timesheet')
  })
})

describe('Lohnbuchhaltung', () => {
  it('zeigt ohne Zeiterfassung „–“ statt Soll/Ist/Saldo, Abwesenheiten bleiben', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const olga = {
      employee_id: 2, employee_number: '102', first_name: 'Olga', last_name: 'Ohne', hire_date: null, termination_date: null,
      entry: false, exit: false, closure: 'OPEN',
      hours: { target_minutes: null, actual_minutes: null, balance_minutes: null, payout_minutes: 0, open_days: 0, holiday_days: 1 },
      surcharges: [], absences: [{ type: 'VACATION', label: 'Urlaub', days: 3 }], changes: [], compensation: null, pay_components: [],
    }
    const tina = { ...olga, employee_id: 1, first_name: 'Tina', last_name: 'Takt', hours: { ...olga.hours, target_minutes: 9600, actual_minutes: 9660, balance_minutes: 60 } }
    mockApi({
      'GET /payroll-accounting/releases': [],
      'GET /payroll-accounting/{month}': {
        month: '2026-10', release: null, includes_pay: true, employees: [olga, tina],
        summary: { employee_count: 2, entries: 0, exits: 0, open_closures: 2 }, changed_since_release: null,
      },
    })
    renderWithProviders(<PayrollAccountingPage />)
    const card = await screen.findByRole('listitem', { name: 'Olga Ohne' })
    expect(within(card).getByText('Soll – · Ist – · Saldo –')).toBeInTheDocument()
    expect(within(card).getByText('Ohne Zeiterfassung')).toBeInTheDocument()
    expect(within(card).getByText('Urlaub: 3 Tage')).toBeInTheDocument()
    expect(within(card).getByText('Feiertage 1')).toBeInTheDocument()
    const tracked = screen.getByRole('listitem', { name: 'Tina Takt' })
    expect(within(tracked).getByText('Soll 160:00 · Ist 161:00 · Saldo +1:00')).toBeInTheDocument()
    expect(within(tracked).queryByText('Ohne Zeiterfassung')).not.toBeInTheDocument()
  })

  it('formatiert leere Dauern als „–“', () => {
    expect(formatHoursMinutes(null)).toBe('–')
    expect(formatHoursMinutes(undefined)).toBe('–')
    expect(formatHoursMinutes(0)).toBe('0:00')
    expect(formatHoursMinutes(90)).toBe('1:30')
  })
})

describe('Monatsabschluss (HR)', () => {
  const base = { first_name: 'Olga', last_name: 'Ohne', employee_number: 'E2', closure_id: 4, dispute_reason: null, open_day_count: 0 }

  it('zeigt ohne Zeiterfassung „–“ statt 0:00 und kennzeichnet den Mitarbeiter', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /period-closures': [
        { ...base, employee_id: 2, status: 'SUBMITTED', delta_minutes: 0, time_tracking: false },
        { ...base, employee_id: 3, first_name: 'Tina', last_name: 'Takt', status: 'SUBMITTED', delta_minutes: 0, time_tracking: true },
        // vor dem Ausschalten abgeschlossen: Saldo bleibt sichtbar
        { ...base, employee_id: 4, first_name: 'Fritz', last_name: 'Früher', status: 'CLOSED', delta_minutes: 90, time_tracking: false },
      ],
    })
    renderWithProviders(<PeriodClosuresPage />)
    const olga = (await screen.findByRole('link', { name: 'Ohne, Olga' })).closest('tr')!
    expect(within(olga).getByText('–')).toBeInTheDocument()
    expect(within(olga).getByText('ohne Zeiterfassung')).toBeInTheDocument()
    const tina = screen.getByRole('link', { name: 'Takt, Tina' }).closest('tr')!
    expect(within(tina).getByText('0:00')).toBeInTheDocument()
    expect(within(tina).queryByText('ohne Zeiterfassung')).not.toBeInTheDocument()
    const fritz = screen.getByRole('link', { name: 'Früher, Fritz' }).closest('tr')!
    expect(within(fritz).getByText('+1:30')).toBeInTheDocument()
  })
})
