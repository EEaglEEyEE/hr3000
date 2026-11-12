/** Analysen: Abwesenheitsquote, Köpfe/FTE und eigene Berichte (Builder, Vorschau, Speichern, Teilen,
 * CSV); Sichtbarkeit je Rolle und Schalter. */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { ReportsPage } from './ReportsPage'
import { RequireAccess } from '../components/layout/RequireAccess'
import { pageAllowed } from '../lib/access'
import { formatCell, monthLabel, shiftMonth } from '../lib/reportFormat'

const FEATURES = { shift_planning_enabled: false, team_calendar_for_employees: false, org_chart_for_employees: false }

const CATALOG = {
  sources: [
    {
      key: 'employees',
      label: 'Mitarbeitende',
      requires_period: false,
      columns: [
        { key: 'last_name', label: 'Nachname', type: 'text', group: 'Stammdaten', operators: ['eq', 'contains', 'is_empty'], options: [], summable: false },
        { key: 'first_name', label: 'Vorname', type: 'text', group: 'Stammdaten', operators: ['eq', 'contains'], options: [], summable: false },
        { key: 'department', label: 'Abteilung', type: 'text', group: 'Stammdaten', operators: ['eq', 'in'], options: [], summable: false },
        { key: 'hire_date', label: 'Eintritt', type: 'date', group: 'Stammdaten', operators: ['gte', 'lt'], options: [], summable: false },
        {
          key: 'status',
          label: 'Status',
          type: 'enum',
          group: 'Stammdaten',
          operators: ['eq', 'in'],
          options: [
            { value: 'ACTIVE', label: 'Aktiv' },
            { value: 'INACTIVE', label: 'Inaktiv' },
          ],
          summable: false,
        },
        { key: 'fte', label: 'Vollzeitanteil (FTE)', type: 'number', group: 'Arbeitszeit', operators: ['gt', 'gte'], options: [], summable: true },
      ],
    },
    {
      key: 'absences',
      label: 'Abwesenheiten',
      requires_period: true,
      columns: [
        { key: 'last_name', label: 'Nachname', type: 'text', group: 'Stammdaten', operators: ['eq'], options: [], summable: false },
        { key: 'first_name', label: 'Vorname', type: 'text', group: 'Stammdaten', operators: ['eq'], options: [], summable: false },
        { key: 'days', label: 'Tage (im Zeitraum)', type: 'number', group: 'Abwesenheit', operators: ['gt'], options: [], summable: true },
        { key: 'half_day', label: 'Halber Tag', type: 'bool', group: 'Abwesenheit', operators: ['eq'], options: [], summable: false },
      ],
    },
  ],
  operators: [],
  max_columns: 30,
  max_filters: 10,
  max_sorts: 3,
  max_range_days: 366,
  max_page_size: 200,
}

function savedReport(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    name: 'Eintritte',
    description: 'Neue Leute',
    definition: { source: 'employees', columns: ['last_name', 'hire_date'], filters: [], sort: [], group_by: null },
    shared: false,
    owner_account_id: 1,
    owner_name: 'hr@example.com',
    mine: true,
    can_edit: true,
    created_at: '2026-11-01T10:00:00',
    updated_at: '2026-11-01T10:00:00',
    ...overrides,
  }
}

const RESULT = {
  columns: [
    { key: 'last_name', label: 'Nachname', type: 'text', summable: false },
    { key: 'hire_date', label: 'Eintritt', type: 'date', summable: false },
    { key: 'fte', label: 'Vollzeitanteil (FTE)', type: 'number', summable: true },
  ],
  rows: [
    ['Alpha', '2020-01-01', 1],
    ['Beta', null, 0.5],
  ],
  total_rows: 2,
  page: 1,
  page_size: 50,
  totals: { fte: 1.5 },
  group_by: null,
  groups: [],
  omitted_columns: [],
  date_from: null,
  date_to: null,
}

function routes(extra: Record<string, unknown> = {}, customReports = true) {
  return {
    'GET /features': { ...FEATURES, custom_reports_enabled: customReports },
    'GET /reports/attention': [],
    'GET /report-builder/catalog': CATALOG,
    'GET /report-builder/reports': [savedReport(), savedReport({ id: 8, name: 'Krank geteilt', shared: true, mine: false, can_edit: false, owner_name: 'Anna Admin' })],
    ...extra,
  }
}

async function openCustomTab() {
  await userEvent.click(await screen.findByRole('tab', { name: 'Eigene Berichte' }))
}

afterEach(() => vi.restoreAllMocks())

describe('Analysen: Reiter je Rolle und Schalter', () => {
  it('zeigt Admin/HR die festen Auswertungen, „Eigene Berichte“ nur bei eingeschaltetem Schalter', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes({}, false))
    renderWithProviders(<ReportsPage />)
    expect(await screen.findByRole('tab', { name: 'Abwesenheitsquote' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Köpfe und FTE' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'Eigene Berichte' })).not.toBeInTheDocument())
  })

  it('zeigt Führungskräften bei eingeschaltetem Schalter nur die eigenen Berichte', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi(routes())
    renderWithProviders(<ReportsPage />)
    expect(await screen.findByRole('button', { name: 'Neuer Bericht' })).toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('verweigert Führungskräften die Seite bei ausgeschaltetem Schalter', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi(routes({}, false))
    renderWithProviders(<ReportsPage />)
    expect(await screen.findByText('Für diese Seite fehlt die Berechtigung.')).toBeInTheDocument()
  })

  it('Seitenschutz öffnet „Analysen“ für Führungskräfte nur mit Schalter', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi(routes())
    renderWithProviders(
      <RequireAccess path="/auswertungen">
        <p>Inhalt</p>
      </RequireAccess>,
    )
    expect(await screen.findByText('Inhalt')).toBeInTheDocument()
  })

  it('Seitenschutz ohne Schalter zeigt den Hinweis', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi(routes({}, false))
    renderWithProviders(
      <RequireAccess path="/auswertungen">
        <p>Inhalt</p>
      </RequireAccess>,
    )
    expect(await screen.findByText('Für diese Seite fehlt die Berechtigung.')).toBeInTheDocument()
    expect(screen.queryByText('Inhalt')).not.toBeInTheDocument()
  })
})

describe('Abwesenheitsquote und Köpfe/FTE', () => {
  it('zeigt die Quote je Monat und Abteilung und schickt die gewählten Kategorien', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(
      routes({
        'GET /reports/absence-rate': {
          date_from: '2026-01-01',
          date_to: '2026-02-28',
          through: '2026-02-28',
          categories: ['SICK', 'CHILD_SICK'],
          months: [
            { month: '2026-01', absence_days: 2, workdays: 40, rate_percent: 5 },
            { month: '2026-02', absence_days: 0, workdays: 0, rate_percent: null },
          ],
          total: { absence_days: 2, workdays: 40, rate_percent: 5 },
          departments: [
            {
              department_id: 3,
              name: 'Vertrieb',
              months: [
                { month: '2026-01', absence_days: 2, workdays: 20, rate_percent: 10 },
                { month: '2026-02', absence_days: 0, workdays: 0, rate_percent: null },
              ],
              total: { absence_days: 2, workdays: 20, rate_percent: 10 },
            },
          ],
        },
      }),
    )
    renderWithProviders(<ReportsPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Abwesenheitsquote' }))
    expect(await screen.findByText('Vertrieb')).toBeInTheDocument()
    expect(screen.getByText('Jan 2026')).toBeInTheDocument()
    expect(screen.getAllByText('5 %').length).toBeGreaterThan(0)
    expect(screen.getAllByText('10 %').length).toBe(2)
    const first = calls.find((c) => c.path === '/reports/absence-rate')!
    expect(first.init.params?.query).toMatchObject({ categories: ['SICK', 'CHILD_SICK'] })
    expect(screen.queryByRole('checkbox', { name: 'Arbeitszeit' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Urlaub' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.path === '/reports/absence-rate').at(-1)!.init.params?.query).toMatchObject({
        categories: ['SICK', 'CHILD_SICK', 'VACATION'],
      }),
    )
  })

  it('fragt ohne Kategorie nicht ab und weist darauf hin', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes({ 'GET /reports/absence-rate': new ApiFailure(422, 'X', 'Fehler') }))
    renderWithProviders(<ReportsPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Abwesenheitsquote' }))
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Krankheit' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Kind krank' }))
    expect(await screen.findByText('Bitte mindestens eine Kategorie wählen.')).toBeInTheDocument()
    const before = calls.filter((c) => c.path === '/reports/absence-rate').length
    await new Promise((r) => setTimeout(r, 20))
    expect(calls.filter((c) => c.path === '/reports/absence-rate').length).toBe(before)
  })

  it('zeigt Köpfe, FTE, Zu- und Abgänge je Monat und je Abteilung', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(
      routes({
        'GET /reports/headcount': {
          date_from: '2026-01-01',
          date_to: '2026-01-31',
          full_time_weekly_hours: 40,
          full_time_from_settings: false,
          months: [
            {
              month: '2026-01',
              as_of: '2026-01-31',
              headcount: 4,
              fte: 2.5,
              joiners: 1,
              leavers: 0,
              departments: [{ department_id: 3, headcount: 2, fte: 1.5 }],
            },
          ],
          departments: [{ department_id: 3, name: 'Vertrieb' }],
        },
      }),
    )
    renderWithProviders(<ReportsPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Köpfe und FTE' }))
    expect(await screen.findByText('2,5')).toBeInTheDocument()
    expect(screen.getByText('2 / 1,5')).toBeInTheDocument()
    expect(screen.getByText(/keine Standard-Arbeitszeit hinterlegt/)).toBeInTheDocument()
  })
})

describe('Eigene Berichte', () => {
  it('listet eigene und geteilte Berichte und löscht nach Rückfrage', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes({ 'DELETE /report-builder/reports/{report_id}': null }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<ReportsPage />)
    await openCustomTab()
    expect(await screen.findByRole('button', { name: 'Eintritte' })).toBeInTheDocument()
    const sharedRow = screen.getByRole('button', { name: 'Krank geteilt' }).closest('tr')!
    expect(within(sharedRow).getByText('geteilt')).toBeInTheDocument()
    expect(within(sharedRow).getByText('Anna Admin')).toBeInTheDocument()
    expect(within(sharedRow).queryByRole('button', { name: 'Löschen' })).not.toBeInTheDocument()
    const ownRow = screen.getByRole('button', { name: 'Eintritte' }).closest('tr')!
    expect(within(ownRow).getByText('Ich')).toBeInTheDocument()
    await userEvent.click(within(ownRow).getByRole('button', { name: 'Löschen' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.init.params?.path?.report_id === 7)).toBe(true))
  })

  it('stellt einen neuen Bericht zusammen, zeigt die Vorschau und speichert ihn geteilt', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(
      routes({
        'POST /report-builder/preview': RESULT,
        'POST /report-builder/reports': (init: ApiInit) => savedReport({ id: 9, ...(init.body as object) }),
      }),
    )
    renderWithProviders(<ReportsPage />)
    await openCustomTab()
    await userEvent.click(await screen.findByRole('button', { name: 'Neuer Bericht' }))
    expect(screen.getByRole('heading', { name: 'Neuer Bericht' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Spalte hinzufügen'), 'fte')
    await userEvent.click(screen.getByRole('button', { name: 'Vorname entfernen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Vollzeitanteil (FTE) nach oben' }))
    await userEvent.click(screen.getByRole('button', { name: 'Filter hinzufügen' }))
    await userEvent.selectOptions(screen.getByLabelText('Filter 1 Spalte'), 'status')
    await userEvent.selectOptions(screen.getByLabelText('Filter 1 Wert'), 'ACTIVE')
    await userEvent.click(screen.getByRole('button', { name: 'Sortierung hinzufügen' }))
    await userEvent.selectOptions(screen.getByLabelText('Richtung 1'), 'desc')
    await userEvent.selectOptions(screen.getByLabelText('Gruppieren nach'), 'department')
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau' }))

    expect(await screen.findByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('1.1.2020')).toBeInTheDocument()
    expect(screen.getByText('1,5')).toBeInTheDocument() // Summe
    const preview = calls.find((c) => c.path === '/report-builder/preview')!
    expect(preview.init.body).toEqual({
      page: 1,
      page_size: 50,
      definition: {
        source: 'employees',
        columns: ['fte', 'last_name'],
        filters: [{ column: 'status', operator: 'eq', value: 'ACTIVE' }],
        sort: [{ column: 'last_name', direction: 'desc' }],
        group_by: 'department',
      },
    })

    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Bitte einen Namen angeben.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Name'), 'Aktive je Abteilung')
    await userEvent.click(screen.getByRole('checkbox', { name: /Mit allen Verwaltungskonten teilen/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Bericht „Aktive je Abteilung“ gespeichert.')).toBeInTheDocument()
    const saved = calls.find((c) => c.method === 'POST' && c.path === '/report-builder/reports')!
    expect(saved.init.body).toMatchObject({ name: 'Aktive je Abteilung', shared: true, description: null, definition: preview.init.body && { source: 'employees' } })
  })

  it('verlangt bei Abwesenheiten einen Zeitraum und sendet ihn mit', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes({ 'POST /report-builder/preview': { ...RESULT, rows: [], total_rows: 0, date_from: '2026-01-01', date_to: '2026-01-31' } }))
    renderWithProviders(<ReportsPage />)
    await openCustomTab()
    await userEvent.click(await screen.findByRole('button', { name: 'Neuer Bericht' }))
    await userEvent.selectOptions(screen.getByLabelText('Datenquelle'), 'absences')
    fireEvent.change(screen.getByLabelText('Zeitraum von'), { target: { value: '2026-01-01' } })
    fireEvent.change(screen.getByLabelText('Zeitraum bis'), { target: { value: '2026-01-31' } })
    await userEvent.click(screen.getByRole('button', { name: 'Filter hinzufügen' }))
    await userEvent.selectOptions(screen.getByLabelText('Filter 1 Spalte'), 'half_day')
    await userEvent.selectOptions(screen.getByLabelText('Filter 1 Wert'), 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau' }))
    expect(await screen.findByText('Keine Zeilen.')).toBeInTheDocument()
    const body = calls.find((c) => c.path === '/report-builder/preview')!.init.body as Record<string, unknown>
    expect(body).toMatchObject({
      date_from: '2026-01-01',
      date_to: '2026-01-31',
      definition: { source: 'absences', columns: ['last_name', 'first_name'], filters: [{ column: 'half_day', operator: 'eq', value: true }] },
    })
  })

  it('führt einen geteilten Bericht über den gespeicherten Stand aus und meldet ausgelassene Spalten', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(
      routes({
        'POST /report-builder/reports/{report_id}/run': { ...RESULT, omitted_columns: ['IBAN'] },
        'POST /report-builder/preview': RESULT,
      }),
    )
    renderWithProviders(<ReportsPage />)
    await openCustomTab()
    await userEvent.click(await screen.findByRole('button', { name: 'Krank geteilt' }))
    expect(screen.queryByRole('button', { name: 'Speichern' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Als neuen Bericht speichern' })).toBeInTheDocument()
    expect(screen.getByText(/ändern können ihn nur Besitzer und Admins/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau' }))
    expect(await screen.findByText('Ohne Berechtigung ausgelassen: IBAN')).toBeInTheDocument()
    const run = calls.find((c) => c.path === '/report-builder/reports/{report_id}/run')!
    expect(run.init.params?.path).toEqual({ report_id: 8 })
    expect(run.init.body).toEqual({ page: 1, page_size: 50 })
    // nach einer Änderung: Vorschau der geänderten Definition
    await userEvent.selectOptions(screen.getByLabelText('Spalte hinzufügen'), 'fte')
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/report-builder/preview')).toBe(true))
  })

  it('zeigt Fehler des Servers (z. B. fehlende Berechtigung) an', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes({ 'POST /report-builder/preview': new ApiFailure(403, 'REPORT_COLUMN_FORBIDDEN', 'Keine Berechtigung für die Spalte „IBAN“.') }))
    renderWithProviders(<ReportsPage />)
    await openCustomTab()
    await userEvent.click(await screen.findByRole('button', { name: 'Neuer Bericht' }))
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau' }))
    expect(await screen.findByText('Keine Berechtigung für die Spalte „IBAN“.')).toBeInTheDocument()
  })

  it('blättert in der Vorschau und zeigt Gruppensummen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(
      routes({
        'POST /report-builder/preview': (init: ApiInit) => ({
          ...RESULT,
          total_rows: 120,
          page: (init.body as { page: number }).page,
          group_by: 'last_name',
          groups: [{ label: 'Alpha', count: 1, sums: { fte: 1 } }, { label: '', count: 1, sums: { fte: 0.5 } }],
        }),
      }),
    )
    renderWithProviders(<ReportsPage />)
    await openCustomTab()
    await userEvent.click(await screen.findByRole('button', { name: 'Neuer Bericht' }))
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau' }))
    expect(await screen.findByText('Seite 1 von 3')).toBeInTheDocument()
    expect(screen.getByText('(leer)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
    expect(await screen.findByText('Seite 2 von 3')).toBeInTheDocument()
    expect((calls.filter((c) => c.path === '/report-builder/preview').at(-1)!.init.body as { page: number }).page).toBe(2)
  })

  it('lädt die CSV vom Server', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes())
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('x', { status: 200, headers: { 'Content-Disposition': 'attachment; filename="Eintritte.csv"' } }))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    renderWithProviders(<ReportsPage />)
    await openCustomTab()
    await userEvent.click(await screen.findByRole('button', { name: 'Eintritte' }))
    await userEvent.click(screen.getByRole('button', { name: 'CSV exportieren' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toBe('/api/report-builder/reports/7/export')
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))).toEqual({ page: 1, page_size: 50 })
  })

  it('meldet einen fehlgeschlagenen CSV-Export', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes())
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Der Bericht hätte mehr als 20.000 Zeilen.', code: 'RESULT_TOO_LARGE' }), { status: 400 }),
    )
    renderWithProviders(<ReportsPage />)
    await openCustomTab()
    await userEvent.click(await screen.findByRole('button', { name: 'Neuer Bericht' }))
    await userEvent.click(screen.getByRole('button', { name: 'CSV exportieren' }))
    expect(await screen.findByText('Der Bericht hätte mehr als 20.000 Zeilen.')).toBeInTheDocument()
  })
})

describe('Helfer', () => {
  it('pageAllowed: Rechte-Tabelle oder Schalter', () => {
    const supervisor = { isAdmin: false, isFullHr: false, canPayroll: false }
    expect(pageAllowed('/auswertungen', supervisor)).toBe(false)
    expect(pageAllowed('/auswertungen', supervisor, { custom_reports_enabled: true })).toBe(true)
    expect(pageAllowed('/lohn-export', supervisor, { custom_reports_enabled: true })).toBe(false)
    expect(pageAllowed('/auswertungen', { ...supervisor, isFullHr: true })).toBe(true)
    expect(pageAllowed('/mitarbeiter', supervisor)).toBe(true)
  })

  it('formatiert Monate und Zellen', () => {
    expect(monthLabel('2026-03')).toBe('Mär 2026')
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-11', 13)).toBe('2027-12')
    expect(formatCell('text', null)).toBe('–')
    expect(formatCell('text', '')).toBe('–')
    expect(formatCell('bool', true)).toBe('Ja')
    expect(formatCell('bool', false)).toBe('Nein')
    expect(formatCell('number', 1234.5)).toBe('1.234,5')
    expect(formatCell('date', '2026-03-01')).toBe('1.3.2026')
    expect(formatCell('enum', 'Aktiv')).toBe('Aktiv')
  })
})
