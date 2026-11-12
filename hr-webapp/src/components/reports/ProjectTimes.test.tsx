/** Projektzeiterfassung (A16): Einstellungen „Projekte & Kunden“, Projekt im Stundenzettel, Projekt beim
 * Korrigieren, Antragsanzeige und die Auswertung „Projektzeiten“ (auch für Führungskräfte). */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Project, ProjectTimes } from '../../api/queries/projects'
import type { TimeEntryWeek } from '../../api/queries/timeEntries'
import { ReportsPage } from '../../pages/ReportsPage'
import { SettingsPage } from '../../pages/SettingsPage'
import { settings } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { PendingCorrectionRequests } from '../punches/CorrectionRequests'
import { PunchHistoryTab } from '../punches/PunchHistoryTab'
import { TimeSheetCard } from '../punches/TimeSheetCard'

const csv = vi.hoisted(() => ({ downloadCsv: vi.fn() }))
vi.mock('../../lib/csv', () => csv)

afterEach(() => {
  vi.useRealTimers()
  csv.downloadCsv.mockReset()
})

const FEATURES = { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true }

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 1, name: 'Netz', number: 'P-1', customer_id: 3, customer_name: 'Stadtwerke', cost_center_id: null, cost_center_label: null,
    billable: true, active: true, valid_from: null, valid_to: null, in_use: false, ...overrides,
  }
}

function renderSettings(route = '/einstellungen/projekte') {
  return renderWithProviders(
    <Routes>
      <Route path="/einstellungen/:seite?" element={<SettingsPage />} />
    </Routes>,
    { route },
  )
}

describe('Einstellungen → Projekte & Kunden', () => {
  it('Admin schaltet Projektzeiten ein und legt Kunde und Projekt an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    let current = settings()
    const calls = mockApi({
      'GET /settings': () => current,
      'PATCH /settings': (init: ApiInit) => {
        current = { ...current, ...(init.body as object) }
        return current
      },
      'GET /features': FEATURES,
      'GET /customers': [{ id: 3, name: 'Stadtwerke', active: true, project_count: 1 }],
      'GET /projects': [project({ in_use: true }), project({ id: 2, name: 'Intern', number: null, customer_id: null, customer_name: null, billable: false })],
      'GET /cost-centers': [{ id: 9, code: '4711', name: 'Bau', archived: false }],
      'POST /customers': { id: 4, name: 'Bäckerei', active: true, project_count: 0 },
      'POST /projects': project({ id: 5 }),
      'DELETE /projects/{project_id}': null,
      'PATCH /projects/{project_id}': project(),
    })
    renderSettings()
    const sent = (method: string, path: string) =>
      calls
        .filter((c) => c.method === method && c.path === path)
        .map((c) => Object.fromEntries(Object.entries((c.init.body ?? {}) as object).filter(([k]) => !k.startsWith('clear_'))))

    const toggle = await screen.findByRole('checkbox', { name: /Projektzeiten/ })
    expect(toggle).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Projekt ist Pflicht/ })).toBeDisabled()
    await userEvent.click(toggle)
    await waitFor(() => expect(sent('PATCH', '/settings').at(-1)).toEqual({ project_times_enabled: true }))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /Projekt ist Pflicht/ })).toBeEnabled())

    await userEvent.type(screen.getByLabelText('Name', { selector: '#customer-name' }), 'Bäckerei')
    await userEvent.click(screen.getByRole('button', { name: 'Kunde hinzufügen' }))
    await waitFor(() => expect(sent('POST', '/customers').at(-1)).toEqual({ name: 'Bäckerei', active: true }))

    // benutztes Projekt lässt sich nicht löschen, das andere schon
    const rows = screen.getAllByRole('row')
    const netzRow = rows.find((r) => within(r).queryByText('Netz'))!
    expect(within(netzRow).getByRole('button', { name: 'Löschen' })).toBeDisabled()
    const internRow = rows.find((r) => within(r).queryByText('Intern'))!
    expect(within(internRow).getByText('Nein')).toBeInTheDocument()
    await userEvent.click(within(internRow).getByRole('button', { name: 'Löschen' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.init.params?.path?.project_id === 2)).toBe(true))

    await userEvent.type(screen.getByLabelText('Name', { selector: '#project-name' }), 'Neubau')
    await userEvent.type(screen.getByLabelText('Nummer (optional)'), ' P-9 ')
    await userEvent.selectOptions(screen.getByLabelText('Kunde (optional)'), '3')
    await userEvent.selectOptions(screen.getByLabelText('Kostenstelle (optional)'), '9')
    await userEvent.click(screen.getByLabelText('Abrechenbar'))
    await userEvent.click(screen.getByRole('button', { name: 'Projekt hinzufügen' }))
    await waitFor(() =>
      expect(sent('POST', '/projects').at(-1)).toEqual({
        name: 'Neubau', number: 'P-9', customer_id: 3, cost_center_id: 9, billable: false, valid_from: null, valid_to: null, active: true,
      }),
    )
    // bearbeiten: Werte übernehmen, Nummer leeren
    await userEvent.click(within(netzRow).getByRole('button', { name: 'Bearbeiten' }))
    expect(screen.getByLabelText('Name', { selector: '#project-name' })).toHaveValue('Netz')
    await userEvent.clear(screen.getByLabelText('Nummer (optional)'))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(sent('PATCH', '/projects/{project_id}').at(-1)).toMatchObject({ name: 'Netz', number: null, customer_id: 3 }))
  })

  it('HR pflegt Projekte, sieht aber keine Schalter', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /features': { ...FEATURES, project_times_enabled: true }, 'GET /customers': [], 'GET /projects': [], 'GET /cost-centers': [] })
    renderSettings()
    expect(await screen.findByRole('button', { name: 'Projekt hinzufügen' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /Projektzeiten/ })).not.toBeInTheDocument()
  })
})

function week(overrides: Partial<TimeEntryWeek> = {}): TimeEntryWeek {
  const days = ['2026-03-02', '2026-03-03', '2026-03-04', '2026-03-05', '2026-03-06', '2026-03-07', '2026-03-08']
  return {
    enabled: true, approval_required: false, backdate_days: 7, earliest_date: '2026-02-25', today: '2026-03-04', timezone: 'Europe/Berlin',
    projects_enabled: true, project_required: true,
    projects: [
      { id: 1, label: 'P-1 Netz (Stadtwerke)', valid_from: null, valid_to: null },
      { id: 2, label: 'Alt', valid_from: null, valid_to: '2026-03-01' },
    ],
    project_names: { 7: 'P-7 Archiv' },
    days: days.map((day) => ({ work_date: day, can_enter: day <= '2026-03-04', spans: [], pending: [], actual_minutes: null })),
    ...overrides,
  }
}

describe('Stundenzettel mit Projekten', () => {
  it('ordnet Arbeitszeiten Projekten zu (Pflicht, nur gültige Projekte) und zeigt sie an', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    const data = week()
    data.days[0] = {
      ...data.days[0],
      spans: [{ kind: 'WORK', start: '2026-03-02T07:00:00', end: '2026-03-02T08:00:00', source: 'SELF_ENTRY', punch_id: 1, deletable: false, project_id: 7, note: 'Ablage' }],
    }
    const posts: unknown[] = []
    mockApi({
      'GET /me/time-entries': data,
      'POST /me/time-entries': (init: ApiInit) => {
        posts.push(init.body)
        return { status: 'APPLIED', punch_ids: [] }
      },
    })
    renderWithProviders(<TimeSheetCard />)
    expect(await screen.findByText(/P-7 Archiv – Ablage/)).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: /Eintragen/ })[1])
    const select = screen.getByLabelText('Projekt')
    // „Alt“ galt nur bis 01.03.
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Projekt wählen …', 'P-1 Netz (Stadtwerke)'])
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Bitte jeder Arbeitszeit ein Projekt zuordnen.')).toBeInTheDocument()
    expect(posts).toHaveLength(0)
    await userEvent.selectOptions(select, '1')
    await userEvent.type(screen.getByLabelText('Tätigkeit'), 'Planung')
    await userEvent.click(screen.getByRole('button', { name: 'Pause hinzufügen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toEqual({
      work_date: '2026-03-03',
      comment: null,
      spans: [
        { kind: 'WORK', start: '08:00', end: '12:00', end_next_day: false, project_id: 1, note: 'Planung' },
        { kind: 'BREAK', start: '09:45', end: '10:15', end_next_day: false },
      ],
    })
  })
})

describe('Projekt bei Korrekturen und Anträgen', () => {
  it('HR ändert das Projekt am „Kommen“', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /features': { ...FEATURES, project_times_enabled: true },
      'GET /projects': [project(), project({ id: 2, name: 'Intern', number: null, active: false })],
      'GET /employees/{employee_id}/punches': [
        { id: 10, employee_id: 7, location_id: 1, punch_type: 'COME', timestamp_utc: '2026-03-02T07:00:00', source: 'SELF_ENTRY', device_id: null,
          created_by_account_id: null, corrected: false, correction_reason: null, project_id: 1, activity_note: 'Plan' },
        { id: 11, employee_id: 7, location_id: 1, punch_type: 'GO', timestamp_utc: '2026-03-02T11:00:00', source: 'SELF_ENTRY', device_id: null,
          created_by_account_id: null, corrected: false, correction_reason: null, project_id: null, activity_note: null },
      ],
      'PATCH /punches/{punch_id}': {},
    })
    renderWithProviders(<PunchHistoryTab employeeId={7} />)
    expect(await screen.findByText('P-1 Netz – Plan')).toBeInTheDocument()
    expect(screen.getAllByText('Selbst eingetragen')).toHaveLength(2)
    // „Gehen“: kein Projektfeld
    await userEvent.click(screen.getAllByRole('button', { name: 'Korrigieren' })[0])
    expect(screen.queryByLabelText('Projekt')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await userEvent.click(screen.getAllByRole('button', { name: 'Korrigieren' })[1])
    const select = await screen.findByLabelText('Projekt')
    expect(select).toHaveValue('1')
    expect(within(select).getByRole('option', { name: 'Intern (inaktiv)' })).toBeInTheDocument()
    await userEvent.selectOptions(select, '')
    await userEvent.type(screen.getByLabelText('Begründung'), 'falsches Projekt')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    expect(calls.find((c) => c.method === 'PATCH')!.init.body).toMatchObject({ project_id: null, activity_note: 'Plan', correction_reason: 'falsches Projekt' })
  })

  it('zeigt Projekt und Tätigkeit im Antrag', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /punch-correction-requests': [{
        id: 1, employee_id: 7, employee_name: 'Muster, Erika', work_date: '2026-03-02', kind: 'TIME_ENTRY', reason: '', status: 'PENDING',
        created_at: null, decided_at: null, decision_note: null, project_names: { 1: 'P-1 Netz' },
        items: [
          { punch_type: 'COME', time: '08:00', next_day: false, project_id: 1, note: 'Plan' },
          { punch_type: 'GO', time: '12:00', next_day: false },
        ],
      }],
    })
    renderWithProviders(<PendingCorrectionRequests />)
    expect(await screen.findByText('08:00–12:00 (P-1 Netz – Plan)')).toBeInTheDocument()
  })
})

const TIMES: ProjectTimes = {
  date_from: '2026-03-01', date_to: '2026-03-31', total_minutes: 630, billable_minutes: 570, non_billable_minutes: 60,
  rows: [
    { employee_id: 1, first_name: 'Erika', last_name: 'Muster', employee_number: 'P1', project_id: 1, project_name: 'Netz', project_number: 'P-1',
      customer_id: 3, customer_name: 'Stadtwerke', cost_center: '10 Bau', billable: true, minutes: 450 },
    { employee_id: 1, first_name: 'Erika', last_name: 'Muster', employee_number: 'P1', project_id: 2, project_name: 'Intern', project_number: null,
      customer_id: null, customer_name: null, cost_center: null, billable: false, minutes: 60 },
    { employee_id: 2, first_name: 'Otto', last_name: 'Other', employee_number: 'P2', project_id: 1, project_name: 'Netz', project_number: 'P-1',
      customer_id: 3, customer_name: 'Stadtwerke', cost_center: '10 Bau', billable: true, minutes: 120 },
  ],
}

describe('Analysen → Projektzeiten', () => {
  it('gruppiert nach Projekt, Kunde und Mitarbeiter und exportiert CSV', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-03-15T12:00:00Z'))
    const calls = mockApi({
      'GET /features': { ...FEATURES, project_times_enabled: true },
      'GET /reports/project-times': TIMES,
      'GET /reports/attention': [],
    })
    renderWithProviders(<ReportsPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Projektzeiten' }))
    expect(await screen.findByText('Gesamt: 10:30 Std.')).toBeInTheDocument()
    expect(screen.getByText('Abrechenbar: 9:30 Std.')).toBeInTheDocument()
    expect(calls.find((c) => c.path === '/reports/project-times')!.init.params?.query).toEqual({ from: '2026-03-01', to: '2026-03-31' })
    const netz = screen.getByText('P-1 Netz').closest('tr')!
    expect(within(netz).getByText('9:30')).toBeInTheDocument()
    expect(within(netz).getByText('alles')).toBeInTheDocument()
    expect(within(screen.getByText('Intern').closest('tr')!).getByText('nichts')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Kunde' }))
    expect(within(screen.getByText('Ohne Kunde').closest('tr')!).getByText('1:00')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mitarbeiter' }))
    const erika = screen.getByText('Muster, Erika').closest('tr')!
    expect(within(erika).getByText('8:30')).toBeInTheDocument()
    expect(within(erika).getByText('7:30 Std.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'CSV exportieren' }))
    expect(csv.downloadCsv).toHaveBeenCalledWith('projektzeiten.csv', expect.arrayContaining(['Projekt', 'Abrechenbar', 'Stunden']), expect.any(Array))
    expect(csv.downloadCsv.mock.calls[0][2][0]).toEqual(['P-1', 'Netz', 'Stadtwerke', '10 Bau', 'ja', 'P1', 'Muster', 'Erika', '7.50'])
  })

  it('Führungskräfte sehen mit Projektzeiten nur diese Auswertung', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({
      'GET /features': { ...FEATURES, project_times_enabled: true },
      'GET /reports/project-times': { ...TIMES, rows: [], total_minutes: 0, billable_minutes: 0, non_billable_minutes: 0 },
    })
    renderWithProviders(<ReportsPage />)
    expect(await screen.findByText('Keine Projektzeiten im Zeitraum.')).toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('Führungskräfte mit beiden Schaltern bekommen zwei Reiter', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({
      'GET /features': { ...FEATURES, project_times_enabled: true, custom_reports_enabled: true },
      'GET /reports/project-times': TIMES,
      'GET /report-builder/catalog': { sources: [], operators: [], max_page_size: 200, max_range_days: 366 },
      'GET /report-builder/reports': [],
    })
    renderWithProviders(<ReportsPage />)
    expect(await screen.findByRole('tab', { name: 'Projektzeiten' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Eigene Berichte' })).toBeInTheDocument()
  })
})
