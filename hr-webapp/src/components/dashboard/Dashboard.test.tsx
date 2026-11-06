import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { dashboard, dashboardMe, hrTodoRoutes, team, type DashboardMe } from '../../test/fixtures'
import { Dashboard } from './Dashboard'

function punchCard() {
  return screen.getByText(/^Stempeln \(Home-Office/).closest('div.rounded-md') as HTMLElement
}

function punchButtons(): string[] {
  return within(punchCard())
    .getAllByRole('button')
    .map((button) => button.textContent ?? '')
}

async function renderAsEmployee(me: Partial<DashboardMe>, extraRoutes: Record<string, unknown> = {}) {
  loginAs({ kind: 'employee', employeeId: 5 })
  const calls = mockApi({ 'GET /dashboard': dashboard({ me: dashboardMe(me) }), ...extraRoutes })
  renderWithProviders(<Dashboard />)
  await screen.findByText('Hallo Erika')
  return calls
}

describe('Stempel-Karte (Web-Login)', () => {
  it('fehlt, solange der Mandant das Stempeln im Web-Login nicht erlaubt', async () => {
    await renderAsEmployee({ portal_punching: false })
    expect(screen.queryByText(/^Stempeln \(Home-Office/)).not.toBeInTheDocument()
  })

  it.each([
    { status: null, flags: {}, expected: ['Kommen'] },
    { status: 'COMPLETE', flags: {}, expected: ['Kommen'] },
    { status: 'PRESENT', flags: { break_buttons: true, errand_buttons: true }, expected: ['Gehen', 'Pause Start', 'Dienstgang Start'] },
    { status: 'PRESENT', flags: { break_buttons: true, errand_buttons: false }, expected: ['Gehen', 'Pause Start'] },
    { status: 'PRESENT', flags: { break_buttons: false, errand_buttons: true }, expected: ['Gehen', 'Dienstgang Start'] },
    { status: 'PRESENT', flags: { break_buttons: false, errand_buttons: false }, expected: ['Gehen'] },
    { status: 'ON_BREAK', flags: {}, expected: ['Pause Ende'] },
    { status: 'ON_ERRAND', flags: {}, expected: ['Dienstgang Ende'] },
    { status: 'ERROR', flags: {}, expected: ['Kommen', 'Gehen'] },
  ] as const)('zeigt bei Status $status nur die passenden Aktionen $expected', async ({ status, flags, expected }) => {
    await renderAsEmployee({ portal_punching: true, today_status: status, ...flags })
    expect(punchButtons()).toEqual(expected)
  })

  it('weist bei widersprüchlichen Buchungen auf den Korrekturantrag hin', async () => {
    await renderAsEmployee({ portal_punching: true, today_status: 'ERROR' })
    expect(within(punchCard()).getByText(/widersprüchlich/)).toBeInTheDocument()
  })

  it('stempelt mit Serverzeit, meldet Erfolg und lädt den neuen Stand', async () => {
    let status: DashboardMe['today_status'] = null
    loginAs({ kind: 'employee', employeeId: 5 })
    const calls = mockApi({
      'GET /dashboard': () => dashboard({ me: dashboardMe({ portal_punching: true, today_status: status }) }),
      'POST /me/punches': () => {
        status = 'PRESENT'
        return { id: 1, employee_id: 5, punch_type: 'COME', source: 'PORTAL', timestamp_utc: '2026-10-21T06:27:00' }
      },
    })
    renderWithProviders(<Dashboard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Kommen' }))

    const post = calls.find((call) => call.method === 'POST')
    // Nur die Art wird gesendet – keine Uhrzeit vom Browser.
    expect(post?.path).toBe('/me/punches')
    expect(post?.init.body).toEqual({ punch_type: 'COME' })
    expect(await screen.findByText(/^Kommen um \d{2}:\d{2} erfasst\.$/)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Gehen' })).toBeInTheDocument()
    expect(calls.filter((call) => call.path === '/dashboard').length).toBeGreaterThanOrEqual(2)
  })

  it('sperrt die Knöpfe, solange die Stempelung läuft (kein Doppelklick)', async () => {
    let release: (value: unknown) => void = () => {}
    await renderAsEmployee(
      { portal_punching: true },
      { 'POST /me/punches': () => new Promise((resolve) => (release = resolve)) },
    )
    const button = screen.getByRole('button', { name: 'Kommen' })
    await userEvent.click(button)
    expect(button).toBeDisabled()
    release({ id: 1, employee_id: 5, punch_type: 'COME', source: 'PORTAL', timestamp_utc: '2026-10-21T06:27:00' })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kommen' })).toBeEnabled())
  })

  it('zeigt die Fehlermeldung des Servers und gibt die Knöpfe wieder frei', async () => {
    await renderAsEmployee(
      { portal_punching: true },
      { 'POST /me/punches': new ApiFailure(409, 'PUNCH_DUPLICATE', 'Diese Stempelung wurde gerade erst erfasst.') },
    )
    await userEvent.click(screen.getByRole('button', { name: 'Kommen' }))
    expect(await screen.findByText('Diese Stempelung wurde gerade erst erfasst.')).toBeInTheDocument()
    expect(screen.queryByText(/erfasst\.$/, { selector: '.text-emerald-700' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kommen' })).toBeEnabled()
  })
})

describe('Startseite für Admin-Konten ohne Mitarbeiter', () => {
  it('erklärt, warum keine Stempel-Karte erscheint', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /dashboard': dashboard({ portal_punching_enabled: true, team: team() }), ...hrTodoRoutes() })
    renderWithProviders(<Dashboard />)
    expect(await screen.findByText('Stempeln ist mit diesem Konto nicht möglich')).toBeInTheDocument()
    expect(screen.queryByText(/^Stempeln \(Home-Office/)).not.toBeInTheDocument()
  })

  it('zeigt keinen Hinweis, wenn das Stempeln im Web-Login aus ist', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /dashboard': dashboard({ portal_punching_enabled: false, team: team() }), ...hrTodoRoutes() })
    renderWithProviders(<Dashboard />)
    await screen.findByText('Zu klären')
    expect(screen.queryByText('Stempeln ist mit diesem Konto nicht möglich')).not.toBeInTheDocument()
  })
})

describe('Kacheln "Zu erledigen" und "Heute"', () => {
  it('blendet Urlaubsanträge aus, wenn Anträge abgeschaltet und keine offen sind', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /dashboard': dashboard({ absence_requests_enabled: false, team: team() }), ...hrTodoRoutes() })
    renderWithProviders(<Dashboard />)
    await screen.findByText('Zu klären')
    expect(screen.queryByText('Urlaubsanträge')).not.toBeInTheDocument()
  })

  it('zeigt Urlaubsanträge weiter, solange noch alte Anträge offen sind', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /dashboard': dashboard({ absence_requests_enabled: false, team: team() }),
      ...hrTodoRoutes({ pendingAbsences: [{ id: 1 }, { id: 2 }] }),
    })
    renderWithProviders(<Dashboard />)
    const tile = (await screen.findByText('Urlaubsanträge')).closest('a') as HTMLElement
    await waitFor(() => expect(within(tile).getByText('2')).toBeInTheDocument())
    expect(tile).toHaveAttribute('href', '/zu-klaeren/urlaubsantraege')
  })

  it('zählt offene Tage und überschrittene Monatsgrenzen in "Zu klären"', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /dashboard': dashboard({ team: team() }),
      ...hrTodoRoutes({
        openDays: [
          { employee_id: 2, first_name: 'Max', last_name: 'B', location_id: 1, work_date: '2026-10-20', status: 'OPEN_MISSING_PUNCH', flags: [], times: '' },
        ],
        caps: [
          { employee_id: 3, first_name: 'A', last_name: 'Z', cap_minutes: 600, actual_minutes: 700, exceeded: true },
          { employee_id: 4, first_name: 'B', last_name: 'Y', cap_minutes: 600, actual_minutes: 560, exceeded: false },
        ],
      }),
    })
    renderWithProviders(<Dashboard />)
    const tile = (await screen.findByText('Zu klären')).closest('a') as HTMLElement
    await waitFor(() => expect(within(tile).getByText('2')).toBeInTheDocument())
  })

  it('zeigt die Gruppe "Dienstgang" nur, wenn jemand unterwegs ist', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /dashboard': dashboard({ team: team({ present: [{ employee_id: 1, name: 'Erika Muster' }], visible_employees: 2 }) }),
      ...hrTodoRoutes(),
    })
    const { unmount } = renderWithProviders(<Dashboard />)
    await screen.findByText('Erika Muster')
    expect(screen.queryByText(/^Dienstgang/)).not.toBeInTheDocument()
    unmount()

    mockApi({
      'GET /dashboard': dashboard({ team: team({ on_errand: [{ employee_id: 2, name: 'Max Beispiel' }], visible_employees: 2 }) }),
      ...hrTodoRoutes(),
    })
    renderWithProviders(<Dashboard />)
    expect(await screen.findByText('Max Beispiel')).toBeInTheDocument()
    expect(screen.getByText(/^Dienstgang/)).toBeInTheDocument()
  })
})
