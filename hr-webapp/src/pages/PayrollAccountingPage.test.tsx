/** Seite „Lohnbuchhaltung“: aktueller Stand, Freigeben (mit Warnung), Lohnbüro-Sicht, Rücknahme. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { PayrollAccountingPage } from './PayrollAccountingPage'

const LIA = {
  employee_id: 1,
  employee_number: '100',
  first_name: 'Lia',
  last_name: 'Lohn',
  hire_date: '2026-10-01',
  termination_date: null,
  entry: true,
  exit: false,
  closure: 'OPEN',
  hours: { target_minutes: 9600, actual_minutes: 9000, balance_minutes: -600, payout_minutes: 0, open_days: 2, holiday_days: 0 },
  surcharges: [{ name: 'Nacht', minutes: 90 }],
  absences: [{ type: 'VACATION', label: 'Urlaub', days: 2 }],
  changes: [{ date: '2026-10-01', kind: 'ENTRY', text: 'Eintritt' }],
  compensation: { pay_type: 'MONTHLY', amount: '3500.00', currency: 'EUR', valid_from: '2026-10-01' },
  pay_components: [{ name: 'Zulage Fahrtkosten', amount: '50.00' }],
}
const MAX = { ...LIA, employee_id: 2, employee_number: '101', first_name: 'Max', last_name: 'Muster', entry: false, exit: true, closure: 'CLOSED', changes: [] }
const SUMMARY = { employee_count: 2, entries: 1, exits: 1, open_closures: 1 }
const RELEASE = {
  month: '2026-10', released_at: '2026-11-05T09:00:00', released_by: 'admin@example.com', employee_count: 2, open_closures: 1, has_datev: true,
}

function live(month = '2026-10') {
  return { month, release: null, includes_pay: true, employees: [LIA, MAX], summary: SUMMARY, changed_since_release: null }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('Lohnbuchhaltung', () => {
  it('zeigt den aktuellen Stand des Vormonats mit allen Angaben', async () => {
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-11-11T10:00:00Z') })
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /payroll-accounting/releases': [], 'GET /payroll-accounting/{month}': live() })
    renderWithProviders(<PayrollAccountingPage />)
    const card = await screen.findByRole('listitem', { name: 'Lia Lohn' })
    expect(within(card).getByText('Neuzugang')).toBeInTheDocument()
    expect(within(card).getByText('Monat offen')).toBeInTheDocument()
    expect(within(card).getByText('Urlaub: 2 Tage')).toBeInTheDocument()
    expect(within(card).getByText('3.500,00 € je Monat')).toBeInTheDocument()
    expect(within(card).getByText('Zulage Fahrtkosten: 50,00 €')).toBeInTheDocument()
    expect(within(card).getByText('1.10.2026: Eintritt')).toBeInTheDocument()
    expect(within(card).getByText('Zuschlag Nacht: 1:30')).toBeInTheDocument()
    expect(screen.getByText(/aktueller Stand, noch nicht freigegeben/)).toBeInTheDocument()
    expect(screen.getByText(/Bei 1 Mitarbeiter\(n\) ist der Monatsabschluss/)).toBeInTheDocument()
    expect(screen.getByRole('listitem', { name: 'Max Muster' })).toHaveTextContent('Austritt')
    expect(calls.find((c) => c.path === '/payroll-accounting/{month}')?.init.params?.path).toEqual({ month: '2026-10' })
    expect(screen.queryByRole('button', { name: 'CSV herunterladen' })).not.toBeInTheDocument()
  })

  it('fragt bei offenen Monatsabschlüssen nach und gibt dann frei', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const bodies: unknown[] = []
    mockApi({
      'GET /payroll-accounting/releases': [],
      'GET /payroll-accounting/{month}': (init: ApiInit) => live(init.params?.path?.month as string),
      'POST /payroll-accounting/{month}/release': (init: ApiInit) => {
        bodies.push(init.body)
        return (init.body as { confirm_open_closures: boolean }).confirm_open_closures
          ? { ...live(), release: RELEASE, changed_since_release: [] }
          : new ApiFailure(409, 'OPEN_CLOSURES', 'Bei 1 Mitarbeiter(n) ist der Monatsabschluss noch nicht abgeschlossen. Trotzdem freigeben?')
      },
    })
    renderWithProviders(<PayrollAccountingPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben' }))
    await waitFor(() => expect(bodies).toEqual([{ confirm_open_closures: false }, { confirm_open_closures: true }]))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Trotzdem freigeben?'))
  })

  it('gibt nicht frei, wenn die Warnung abgelehnt wird', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const calls = mockApi({
      'GET /payroll-accounting/releases': [],
      'GET /payroll-accounting/{month}': live(),
      'POST /payroll-accounting/{month}/release': new ApiFailure(409, 'OPEN_CLOSURES', 'Trotzdem freigeben?'),
    })
    renderWithProviders(<PayrollAccountingPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben' }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1))
  })

  it('markiert bei freigegebenen Monaten, was sich seither geändert hat', async () => {
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-11-11T10:00:00Z') })
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /payroll-accounting/releases': [RELEASE],
      'GET /payroll-accounting/{month}': { ...live(), release: RELEASE, changed_since_release: [1] },
    })
    renderWithProviders(<PayrollAccountingPage />)
    const card = await screen.findByRole('listitem', { name: 'Lia Lohn' })
    expect(within(card).getByText('Seit der Freigabe geändert')).toBeInTheDocument()
    expect(within(screen.getByRole('listitem', { name: 'Max Muster' })).queryByText('Seit der Freigabe geändert')).not.toBeInTheDocument()
    expect(screen.getByText(/freigegeben am/)).toHaveTextContent('admin@example.com')
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/payroll-accounting/{month}' && c.init.params?.query?.compare === true)).toBe(true),
    )
    expect(screen.getByRole('button', { name: 'Freigabe zurücknehmen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'DATEV LODAS herunterladen' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Freigeben' })).not.toBeInTheDocument()
  })

  it('nimmt als Admin die Freigabe zurück', async () => {
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-11-11T10:00:00Z') })
    loginAs({ kind: 'hr', role: 'ADMIN' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const calls = mockApi({
      'GET /payroll-accounting/releases': [RELEASE],
      'GET /payroll-accounting/{month}': { ...live(), release: RELEASE, changed_since_release: [] },
      'DELETE /payroll-accounting/{month}/release': null,
    })
    renderWithProviders(<PayrollAccountingPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Freigabe zurücknehmen' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'DELETE')?.init.params?.path).toEqual({ month: '2026-10' }))
  })

  it('HR mit Vergütung sieht keine Rücknahme', async () => {
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-11-11T10:00:00Z') })
    loginAs({ kind: 'hr', role: 'HR', payroll: true })
    mockApi({
      'GET /payroll-accounting/releases': [RELEASE],
      'GET /payroll-accounting/{month}': { ...live(), release: RELEASE, changed_since_release: [] },
    })
    renderWithProviders(<PayrollAccountingPage />)
    await screen.findByRole('listitem', { name: 'Lia Lohn' })
    expect(screen.queryByRole('button', { name: 'Freigabe zurücknehmen' })).not.toBeInTheDocument()
  })

  it('Lohnbüro (nur lesen) wählt nur freigegebene Monate und lädt Dateien', async () => {
    loginAs({ kind: 'hr', role: 'HR', payroll: true, perms: { PAYROLL: 'VIEW' } })
    const fetchMock = vi.fn(async () => new Response('x', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const calls = mockApi({
      'GET /payroll-accounting/releases': [RELEASE, { ...RELEASE, month: '2026-09', has_datev: false }],
      'GET /payroll-accounting/{month}': (init: ApiInit) => ({
        ...live(init.params?.path?.month as string),
        release: { ...RELEASE, month: init.params?.path?.month },
        changed_since_release: null,
      }),
    })
    renderWithProviders(<PayrollAccountingPage />)
    const select = await screen.findByLabelText('Freigegebener Monat')
    await waitFor(() => expect(select).toHaveValue('2026-10'))
    expect(screen.queryByLabelText('Monat')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Freigeben' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Freigabe zurücknehmen' })).not.toBeInTheDocument()
    // Kein Vergleich mit Live-Daten
    expect(calls.every((c) => c.init.params?.query?.compare !== true)).toBe(true)
    await userEvent.click(await screen.findByRole('button', { name: 'CSV herunterladen' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/payroll-accounting/2026-10/files/csv', expect.anything()))
    await userEvent.selectOptions(select, '2026-09')
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/payroll-accounting/{month}' && c.init.params?.path?.month === '2026-09')).toBe(true),
    )
    vi.unstubAllGlobals()
  })

  it('Lohnbüro ohne Freigaben bekommt einen Hinweis', async () => {
    loginAs({ kind: 'hr', role: 'HR', payroll: true, perms: { PAYROLL: 'VIEW' } })
    const calls = mockApi({ 'GET /payroll-accounting/releases': [] })
    renderWithProviders(<PayrollAccountingPage />)
    expect(await screen.findByText('Es ist noch kein Monat freigegeben.')).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/payroll-accounting/{month}')).toBe(false)
  })

  it('zeigt Fehler des Servers beim Laden', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /payroll-accounting/releases': [],
      'GET /payroll-accounting/{month}': new ApiFailure(400, 'TOO_MANY_EMPLOYEES', 'Mehr als 200 Mitarbeiter im Monat'),
    })
    renderWithProviders(<PayrollAccountingPage />)
    expect(await screen.findByText(/Mehr als 200 Mitarbeiter/)).toBeInTheDocument()
  })
})
