/** Stundenzettel (Zeiten selbst eintragen, A14): Wochenraster, Eintragen mit Pausen, Genehmigung,
 * Zurückziehen/Löschen, Prüfregeln, Anzeige unter „Zu klären“ und die Einstellung. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TimeEntryWeek } from '../../api/queries/timeEntries'
import { SelfServicePage } from '../../pages/SelfServicePage'
import { SettingsPage } from '../../pages/SettingsPage'
import { dashboard, settings } from '../../test/fixtures'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { describeTimeEntry, validateSpans, type SpanDraft } from '../../lib/timeEntries'
import { PendingCorrectionRequests } from './CorrectionRequests'
import { TimeSheetCard } from './TimeSheetCard'

const DAYS = ['2026-03-02', '2026-03-03', '2026-03-04', '2026-03-05', '2026-03-06', '2026-03-07', '2026-03-08']

function week(overrides: Partial<TimeEntryWeek> = {}): TimeEntryWeek {
  return {
    enabled: true,
    approval_required: false,
    backdate_days: 7,
    earliest_date: '2026-02-25',
    today: '2026-03-04',
    timezone: 'Europe/Berlin',
    projects_enabled: false,
    project_required: false,
    projects: [],
    project_names: {},
    days: DAYS.map((day) => ({ work_date: day, can_enter: day <= '2026-03-04', spans: [], pending: [], actual_minutes: null })),
    ...overrides,
  }
}

function withDay(base: TimeEntryWeek, day: string, patch: Partial<TimeEntryWeek['days'][number]>): TimeEntryWeek {
  return { ...base, days: base.days.map((d) => (d.work_date === day ? { ...d, ...patch } : d)) }
}

const span = (start: string, end: string, kind: 'WORK' | 'BREAK' = 'WORK'): SpanDraft => ({ kind, start, end, end_next_day: false })

afterEach(() => vi.useRealTimers())

describe('validateSpans', () => {
  it('prüft Reihenfolge, Überschneidungen und Pausen', () => {
    expect(validateSpans([span('08:00', '12:00'), span('12:00', '16:00')])).toBeNull()
    expect(validateSpans([span('12:00', '08:00')])).toMatch(/Ende muss nach dem Beginn/)
    expect(validateSpans([{ ...span('22:00', '06:00'), end_next_day: true }])).toBeNull()
    expect(validateSpans([span('08:00', '12:00'), span('11:00', '13:00')])).toMatch(/überschneiden/)
    expect(validateSpans([span('08:00', '16:00'), span('10:00', '11:00', 'BREAK'), span('10:30', '10:45', 'BREAK')])).toMatch(/Pausen überschneiden/)
    expect(validateSpans([span('08:00', '12:00'), span('12:00', '12:30', 'BREAK')])).toMatch(/innerhalb einer Arbeitszeit/)
    expect(validateSpans([span('08:00', '12:00', 'BREAK')])).toMatch(/mindestens eine Arbeitszeit/)
    expect(validateSpans([span('', '12:00')])).toMatch(/Beginn und Ende/)
  })
})

describe('describeTimeEntry', () => {
  it('paart Kommen/Gehen und Pausen zu Spannen', () => {
    const items = [
      { punch_type: 'COME' as const, time: '08:00', next_day: false },
      { punch_type: 'BREAK_START' as const, time: '10:00', next_day: false },
      { punch_type: 'BREAK_END' as const, time: '10:15', next_day: false },
      { punch_type: 'GO' as const, time: '12:00', next_day: false },
      { punch_type: 'COME' as const, time: '22:00', next_day: false },
      { punch_type: 'GO' as const, time: '02:00', next_day: true },
    ]
    expect(describeTimeEntry(items)).toBe('08:00–12:00, Pause 10:00–10:15, 22:00–02:00 (Folgetag)')
    expect(describeTimeEntry(items.slice(0, 4), () => 'P-1')).toBe('08:00–12:00 (P-1), Pause 10:00–10:15')
  })
})

describe('Stundenzettel', () => {
  it('zeigt Zeiten, Quelle, offene Anträge und die Wochensumme', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-03-04T12:00:00Z'))
    let data = withDay(week(), '2026-03-02', {
      actual_minutes: 465,
      spans: [
        { kind: 'WORK', start: '2026-03-02T07:00:00', end: '2026-03-02T11:00:00', source: 'KIOSK', punch_id: 1, deletable: false },
        { kind: 'WORK', start: '2026-03-02T11:30:00', end: '2026-03-02T15:30:00', source: 'SELF_ENTRY', punch_id: 3, deletable: true },
      ],
    })
    data = withDay(data, '2026-03-03', {
      pending: [{ request_id: 9, spans: [{ kind: 'WORK', start: '2026-03-03T07:00:00', end: '2026-03-03T08:00:00', deletable: false }] }],
    })
    const calls = mockApi({
      'GET /me/time-entries': data,
      'DELETE /me/time-entries/requests/{request_id}': null,
      'DELETE /me/time-entries/{punch_id}': null,
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<TimeSheetCard />)

    expect(await screen.findByText('Stundenzettel')).toBeInTheDocument()
    expect(screen.getByText(/bis zu 7 Tage rückwirkend/)).toBeInTheDocument()
    expect(screen.getByText(/zählen sofort/)).toBeInTheDocument()
    expect(screen.getByText('08:00–12:00')).toBeInTheDocument()
    expect(screen.getByText('(Tablet)')).toBeInTheDocument()
    expect(screen.getByText('Woche: 7:45 Std.')).toBeInTheDocument()
    expect(screen.getByText('08:00–09:00')).toBeInTheDocument()
    expect(screen.getByText('beantragt')).toBeInTheDocument()
    // nur bis heute eintragbar
    expect(screen.getAllByRole('button', { name: /Eintragen/ })).toHaveLength(3)
    expect(calls.find((c) => c.path === '/me/time-entries')?.init.params?.query).toEqual({ from: '2026-03-02', to: '2026-03-08' })

    await userEvent.click(screen.getByRole('button', { name: 'Zurückziehen' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.init.params?.path?.request_id === 9)).toBe(true))
    await userEvent.click(screen.getByRole('button', { name: '12:30–16:30 löschen' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.init.params?.path?.punch_id === 3)).toBe(true))
    expect(screen.queryByRole('button', { name: '08:00–12:00 löschen' })).not.toBeInTheDocument()
  })

  it('trägt mehrere Zeiten mit Pause ein und meldet Fehler verständlich', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    const posts: unknown[] = []
    let fail = true
    mockApi({
      'GET /me/time-entries': week(),
      'POST /me/time-entries': (init: ApiInit) => {
        posts.push(init.body)
        if (fail) {
          fail = false
          return new ApiFailure(422, 'TIME_ENTRY_OVERLAP', '08:00–12:00 überschneidet sich mit vorhandenen Zeiten.')
        }
        return { status: 'APPLIED', punch_ids: [1, 2] }
      },
    })
    renderWithProviders(<TimeSheetCard />)
    const buttons = await screen.findAllByRole('button', { name: /Eintragen/ })
    await userEvent.click(buttons[0])
    expect(screen.getByText('Zeiten am 2.3.2026')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'weitere Arbeitszeit' }))
    await userEvent.click(screen.getByRole('button', { name: 'Pause hinzufügen' }))
    const ends = screen.getAllByLabelText('Ende')
    await userEvent.clear(ends[2])
    await userEvent.type(ends[2], '13:30')
    // Pause 12:00–13:30 liegt nicht innerhalb einer Arbeitszeit (08–12, 12–17)
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/innerhalb einer Arbeitszeit/)).toBeInTheDocument()
    expect(posts).toHaveLength(0)
    await userEvent.click(screen.getAllByRole('button', { name: 'Zeile entfernen' })[2])
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/überschneidet sich mit vorhandenen Zeiten/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Zeiten für den 2.3.2026 eingetragen.')).toBeInTheDocument()
    expect(posts.at(-1)).toEqual({
      work_date: '2026-03-02',
      comment: null,
      spans: [
        { kind: 'WORK', start: '08:00', end: '12:00', end_next_day: false },
        { kind: 'WORK', start: '12:00', end: '17:00', end_next_day: false },
      ],
    })
  })

  it('schickt mit Genehmigung einen Antrag samt Hinweis', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    const posts: unknown[] = []
    mockApi({
      'GET /me/time-entries': week({ approval_required: true, backdate_days: 0 }),
      'POST /me/time-entries': (init: ApiInit) => {
        posts.push(init.body)
        return { status: 'PENDING', request_id: 4, punch_ids: [] }
      },
    })
    renderWithProviders(<TimeSheetCard />)
    expect(await screen.findByText(/nur für heute/)).toBeInTheDocument()
    expect(screen.getByText(/erst, wenn sie genehmigt sind/)).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: /Eintragen/ })[2])
    await userEvent.click(screen.getByLabelText('Folgetag'))
    await userEvent.type(screen.getByLabelText(/Hinweis für die Genehmigung/), 'Messe')
    await userEvent.click(screen.getByRole('button', { name: 'Zur Genehmigung senden' }))
    expect(await screen.findByText('Zeiten für den 4.3.2026 zur Genehmigung gesendet.')).toBeInTheDocument()
    expect(posts[0]).toMatchObject({ work_date: '2026-03-04', comment: 'Messe', spans: [{ end_next_day: true }] })
  })

  it('blättert wochenweise, aber nicht über die laufende Woche hinaus', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-03-04T12:00:00Z'))
    const calls = mockApi({ 'GET /me/time-entries': week() })
    renderWithProviders(<TimeSheetCard />)
    expect(await screen.findByText('2.3.2026 – 8.3.2026')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Nächste Woche' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Vorige Woche' }))
    await waitFor(() =>
      expect(calls.some((c) => c.init.params?.query?.from === '2026-02-23' && c.init.params?.query?.to === '2026-03-01')).toBe(true),
    )
  })

  it('erscheint nicht, wenn die Firma es nicht nutzt', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    mockApi({ 'GET /me/time-entries': week({ enabled: false }) })
    const { container } = renderWithProviders(<TimeSheetCard />)
    await waitFor(() => expect(screen.queryByText('Lädt…')).not.toBeInTheDocument())
    expect(container).toBeEmptyDOMElement()
  })

  it.each([
    { enabled: false, visible: false },
    { enabled: true, visible: true },
  ])('„Mein Bereich“ zeigt den Stundenzettel nur mit Schalter ($enabled)', async ({ enabled, visible }) => {
    loginAs({ kind: 'employee', employeeId: 7 })
    mockApi({
      'GET /employees/{employee_id}': { id: 7, first_name: 'Erika', last_name: 'Muster', location_id: 1, active: true },
      'GET /dashboard': dashboard({ self_time_entry_enabled: enabled }),
      'GET /me/time-entries': week(),
      'GET /punch-correction-requests': [],
      'GET /employees/{employee_id}/punches': [],
    })
    renderWithProviders(<SelfServicePage />, { route: '/mein-bereich' })
    await userEvent.click(await screen.findByRole('tab', { name: 'Zeiterfassung' }))
    expect(await screen.findByText('Korrektur beantragen')).toBeInTheDocument()
    if (visible) expect(await screen.findByText('Stundenzettel')).toBeInTheDocument()
    else expect(screen.queryByText('Stundenzettel')).not.toBeInTheDocument()
  })
})

describe('Zu klären → Korrekturanträge', () => {
  it('zeigt eingetragene Zeiten als eigene Art', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /punch-correction-requests': [
        {
          id: 1, employee_id: 7, employee_name: 'Muster, Erika', work_date: '2026-03-02', kind: 'TIME_ENTRY', reason: '',
          status: 'PENDING', created_at: null, decided_at: null, decision_note: null,
          items: [
            { punch_type: 'COME', time: '08:00', next_day: false },
            { punch_type: 'GO', time: '12:00', next_day: false },
          ],
        },
        {
          id: 2, employee_id: 7, employee_name: 'Muster, Erika', work_date: '2026-03-03', kind: 'CORRECTION', reason: 'vergessen',
          status: 'PENDING', created_at: null, decided_at: null, decision_note: null,
          items: [{ punch_type: 'GO', time: '17:00', next_day: false }],
        },
      ],
    })
    renderWithProviders(<PendingCorrectionRequests />)
    const timeRow = (await screen.findByText('Zeiten eingetragen')).closest('tr')!
    expect(within(timeRow).getByText('08:00–12:00')).toBeInTheDocument()
    expect(within(timeRow).getByText('–')).toBeInTheDocument()
    const correctionRow = screen.getByText('Korrektur').closest('tr')!
    expect(within(correctionRow).getByText('Gehen 17:00')).toBeInTheDocument()
  })
})

describe('Einstellungen → Stempeln', () => {
  it('schaltet Zeiten selbst eintragen ein und setzt den Zeitraum', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    let current = settings()
    const calls = mockApi({
      'GET /settings': () => current,
      'PATCH /settings': (init: ApiInit) => {
        current = { ...current, ...(init.body as object) }
        return current
      },
      'GET /absence-types': [],
      'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true },
    })
    renderWithProviders(
      <Routes>
        <Route path="/einstellungen/:seite?" element={<SettingsPage />} />
      </Routes>,
      { route: '/einstellungen/stempeln' },
    )
    // gesendete Felder ohne die festen "nicht leeren"-Marker
    const patches = () =>
      calls
        .filter((c) => c.method === 'PATCH')
        .map((c) => Object.fromEntries(Object.entries(c.init.body as object).filter(([key]) => !key.startsWith('clear_'))))
    const toggle = await screen.findByRole('checkbox', { name: 'Zeiten selbst eintragen erlauben' })
    expect(toggle).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Genehmigung nötig/ })).toBeDisabled()
    await userEvent.click(toggle)
    await waitFor(() => expect(patches().at(-1)).toEqual({ self_time_entry_enabled: true }))
    const approval = await screen.findByRole('checkbox', { name: /Genehmigung nötig/ })
    await waitFor(() => expect(approval).toBeEnabled())
    expect(approval).toBeChecked()
    await userEvent.click(approval)
    await waitFor(() => expect(patches().at(-1)).toEqual({ self_time_entry_approval: false }))
    const days = screen.getByLabelText('Rückwirkend eintragen bis Tage')
    await userEvent.clear(days)
    await userEvent.type(days, '63')
    const apply = within(days.closest('div')!).getByRole('button', { name: 'Übernehmen' })
    expect(apply).toBeDisabled()
    await userEvent.clear(days)
    await userEvent.type(days, '14')
    await userEvent.click(apply)
    await waitFor(() => expect(patches().at(-1)).toEqual({ self_time_entry_backdate_days: 14 }))
  })
})
