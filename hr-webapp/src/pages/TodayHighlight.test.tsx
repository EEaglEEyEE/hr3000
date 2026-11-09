/** Hervorhebung von "heute" in Kalender und Anwesenheitsübersicht, inkl. Monats-/Wochen-
 * und Jahreswechsel. Die Systemzeit wird dafür fest eingestellt. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { AttendanceOverviewPage } from './AttendanceOverviewPage'
import { TeamCalendarPage } from './TeamCalendarPage'

function setToday(year: number, month: number, day: number) {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(year, month - 1, day, 10, 0))
}

const EMPLOYEES = [
  { id: 1, first_name: 'Erika', last_name: 'Muster', department_id: null },
  { id: 2, first_name: 'Max', last_name: 'Beispiel', department_id: null },
]

function calendarRoutes() {
  return {
    'GET /locations': [],
    'GET /absence-types': [],
    'GET /team-calendar': (init: ApiInit) => {
      const from = String(init.params?.query?.from)
      return EMPLOYEES.map((e) => ({
        employee_id: e.id,
        first_name: e.first_name,
        last_name: e.last_name,
        department_id: null,
        days: [{ date: from, status: null, absence_type: null, is_birthday: e.id === 1 }],
      }))
    },
  }
}

function todayHeaders() {
  return screen.queryAllByTitle('Heute').filter((element) => element.tagName === 'TH')
}

beforeEach(() => loginAs({ kind: 'hr', role: 'ADMIN' }))

describe('Kalender', () => {
  it('hebt den heutigen Tag im aktuellen Monat hervor (Kopf und Spalte)', async () => {
    setToday(2026, 10, 21)
    const calls = mockApi(calendarRoutes())
    renderWithProviders(<TeamCalendarPage />)
    await screen.findByText('Muster, Erika')

    expect(screen.getByText('Oktober 2026')).toBeInTheDocument()
    const headers = todayHeaders()
    expect(headers).toHaveLength(1)
    expect(headers[0]).toHaveTextContent('21')
    // Spalte 1 = Mitarbeiter, Tag 21 = Spalte 22: beide Zeilen hinterlegt, Nachbartage nicht.
    for (const row of screen.getAllByRole('row').slice(1)) {
      const cells = within(row).getAllByRole('cell')
      expect(cells[21]).toHaveClass('bg-sky-50')
      expect(cells[20]).not.toHaveClass('bg-sky-50')
      expect(cells[22]).not.toHaveClass('bg-sky-50')
    }
    expect(screen.queryByRole('button', { name: 'Heute' })).not.toBeInTheDocument()
    const query = calls.find((call) => call.path === '/team-calendar')?.init.params?.query
    expect(query).toMatchObject({ from: '2026-10-01', to: '2026-10-31' })
  })

  it('zeigt in anderen Monaten keine Hervorhebung, aber einen "Heute"-Knopf zurück', async () => {
    setToday(2026, 10, 21)
    mockApi(calendarRoutes())
    renderWithProviders(<TeamCalendarPage />)
    await screen.findByText('Muster, Erika')

    await userEvent.click(screen.getByRole('button', { name: 'Vorheriger Monat' }))
    expect(await screen.findByText('September 2026')).toBeInTheDocument()
    await screen.findByText('Muster, Erika')
    expect(todayHeaders()).toHaveLength(0)

    await userEvent.click(screen.getByRole('button', { name: 'Heute' }))
    expect(await screen.findByText('Oktober 2026')).toBeInTheDocument()
    await waitFor(() => expect(todayHeaders()).toHaveLength(1))
    expect(screen.queryByRole('button', { name: 'Heute' })).not.toBeInTheDocument()
  })

  it('springt über den Jahreswechsel richtig zurück und wieder zu heute', async () => {
    setToday(2027, 1, 1)
    mockApi(calendarRoutes())
    renderWithProviders(<TeamCalendarPage />)
    await screen.findByText('Muster, Erika')
    expect(screen.getByText('Januar 2027')).toBeInTheDocument()
    expect(todayHeaders()[0]).toHaveTextContent(/^1$/)

    await userEvent.click(screen.getByRole('button', { name: 'Vorheriger Monat' }))
    expect(await screen.findByText('Dezember 2026')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Nächster Monat' }))
    await userEvent.click(screen.getByRole('button', { name: 'Nächster Monat' }))
    expect(await screen.findByText('Februar 2027')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Heute' }))
    expect(await screen.findByText('Januar 2027')).toBeInTheDocument()
  })

  it('hebt den 31. am Monatsende hervor und zeigt Geburtstage', async () => {
    setToday(2026, 12, 31)
    mockApi(calendarRoutes())
    renderWithProviders(<TeamCalendarPage />)
    await screen.findByText('Muster, Erika')
    expect(todayHeaders()[0]).toHaveTextContent('31')
    expect(screen.getByTitle('Geburtstag Erika Muster')).toHaveTextContent('🎂')
  })
})

describe('Anwesenheitsübersicht', () => {
  function attendanceRoutes() {
    return {
      'GET /locations': [],
      'GET /absence-types': [],
      'GET /employees': EMPLOYEES,
      'GET /employees/{employee_id}/timesheet': [],
    }
  }

  it('markiert heute in der aktuellen Woche und lädt genau diese Woche', async () => {
    setToday(2026, 10, 21) // Mittwoch
    const calls = mockApi(attendanceRoutes())
    renderWithProviders(<AttendanceOverviewPage />)
    await screen.findByText('Muster, Erika')

    expect(screen.getByText('19.10. – 25.10.2026')).toBeInTheDocument()
    const headers = todayHeaders()
    expect(headers).toHaveLength(1)
    expect(headers[0]).toHaveTextContent('Heute')
    expect(headers[0]).toHaveTextContent('21.10.')
    expect(screen.queryByRole('button', { name: 'Heute' })).not.toBeInTheDocument()
    await waitFor(() => {
      const timesheetCalls = calls.filter((call) => call.path === '/employees/{employee_id}/timesheet')
      expect(timesheetCalls.map((call) => call.init.params?.path?.employee_id).sort()).toEqual([1, 2])
      expect(timesheetCalls[0].init.params?.query).toEqual({ from: '2026-10-19', to: '2026-10-25' })
    })
  })

  it('ordnet einen Sonntag der laufenden Woche (Montag–Sonntag) zu', async () => {
    setToday(2026, 10, 25) // Sonntag
    mockApi(attendanceRoutes())
    renderWithProviders(<AttendanceOverviewPage />)
    await screen.findByText('Muster, Erika')
    expect(screen.getByText('19.10. – 25.10.2026')).toBeInTheDocument()
    expect(todayHeaders()[0]).toHaveTextContent('25.10.')
  })

  it('zeigt in anderen Wochen keine Hervorhebung und springt mit "Heute" zurück', async () => {
    setToday(2026, 12, 30)
    mockApi(attendanceRoutes())
    renderWithProviders(<AttendanceOverviewPage />)
    await screen.findByText('Muster, Erika')

    await userEvent.click(screen.getByRole('button', { name: 'Nächste Woche' }))
    // Woche über den Jahreswechsel
    expect(await screen.findByText('04.01. – 10.01.2027')).toBeInTheDocument()
    expect(todayHeaders()).toHaveLength(0)
    await userEvent.click(screen.getByRole('button', { name: 'Heute' }))
    expect(await screen.findByText('28.12. – 03.01.2027')).toBeInTheDocument()
    expect(todayHeaders()).toHaveLength(1)
  })
})
