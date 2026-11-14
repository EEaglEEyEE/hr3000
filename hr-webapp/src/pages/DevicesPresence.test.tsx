/** Live-Status unter „Tablets“: online / wird abgefragt / offline, Stand der Warteschlange am Tablet,
 * regelmäßige Abfrage nur solange die Seite offen ist. */
import { act, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PRESENCE_REFETCH_MS } from '../api/queries/devices'
import { ApiFailure, loginAs, mockApi, renderWithProviders } from '../test/utils'
import { DevicesPage } from './DevicesPage'

const base = {
  location_id: 1, rejected_at: null, theme: null, screen_hours_mode: null, screen_on_from: null, screen_on_until: null, mdm_name: null,
}
const frankfurt = { ...base, id: 3, name: 'Kiosk Frankfurt', last_seen: '2026-11-14T12:59:50', bound_at: '2026-11-01T08:00:00' }
const viernheim = { ...base, id: 4, name: 'Kiosk Viernheim', last_seen: '2026-11-14T09:05:00', bound_at: '2026-11-01T08:00:00' }
const spare = { ...base, id: 5, name: 'Ersatzgerät', last_seen: null, bound_at: null }

type Row = { device_id: number; state: 'ONLINE' | 'CHECKING' | 'OFFLINE'; last_seen: string | null; queued_punches: number | null; failed_punches: number | null; screen_off: boolean }

function row(device_id: number, state: Row['state'], extra: Partial<Row> = {}): Row {
  return { device_id, state, last_seen: '2026-11-14T12:59:50', queued_punches: 0, failed_punches: 0, screen_off: false, ...extra }
}

function presence(devices: Row[]) {
  return { checked_at: '2026-11-14T13:00:00', watching_since: '2026-11-14T12:58:00', heartbeat_seconds: 15, online_window_seconds: 45, devices }
}

function api(presenceRoute: unknown, devices: unknown[] = [frankfurt, viernheim, spare]) {
  return mockApi({
    'GET /locations': [{ id: 1, name: 'Frankfurt', timezone: 'Europe/Berlin' }],
    'GET /devices': devices,
    'GET /devices/enrollments': [],
    'GET /devices/enrollment-keys': [],
    'GET /devices/presence': presenceRoute as never,
  })
}

function tableRow(name: string): HTMLElement {
  return screen.getByText(name).closest('tr') as HTMLElement
}

function presenceCalls(calls: ReturnType<typeof mockApi>): number {
  return calls.filter((call) => call.method === 'GET' && call.path === '/devices/presence').length
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Live-Status der Tablets', () => {
  it('zeigt je Tablet online, offline und „kein Gerät gekoppelt“ samt Zusammenfassung', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(presence([row(3, 'ONLINE'), row(4, 'OFFLINE', { last_seen: '2026-11-14T09:05:00' }), row(5, 'OFFLINE', { last_seen: null, queued_punches: null, failed_punches: null })]))
    renderWithProviders(<DevicesPage />)

    const summary = await screen.findByRole('status', { name: 'Live-Status' })
    // Das ungekoppelte Ersatzgerät zählt nicht mit
    expect(within(summary).getByText('1 von 2 Tablets online')).toBeInTheDocument()
    expect(within(summary).getByText(/Stand \d{1,2}:00:00 Uhr/)).toBeInTheDocument()
    expect(within(summary).getByText(/melden sich die Tablets alle 15 Sekunden, sonst alle 15 Minuten/)).toBeInTheDocument()
    expect(within(summary).queryByText(/abgefragt/)).not.toBeInTheDocument()

    expect(screen.getByRole('columnheader', { name: 'Status' })).toBeInTheDocument()
    expect(within(tableRow('Kiosk Frankfurt')).getByText('Online')).toBeInTheDocument()
    const offline = tableRow('Kiosk Viernheim')
    expect(within(offline).getByText('Offline')).toBeInTheDocument()
    expect(within(offline).getByText(/zuletzt gemeldet 14\.11\.26/)).toBeInTheDocument()
    const unpaired = tableRow('Ersatzgerät')
    expect(within(unpaired).getByText('Kein Gerät gekoppelt')).toBeInTheDocument()
    expect(within(unpaired).queryByText('Offline')).not.toBeInTheDocument()
  })

  it('zeigt direkt nach dem Öffnen „wird abgefragt“ statt vorschnell offline', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(presence([row(3, 'CHECKING', { last_seen: '2026-11-14T12:51:00' }), row(4, 'CHECKING', { last_seen: null })]), [frankfurt, viernheim])
    renderWithProviders(<DevicesPage />)

    const summary = await screen.findByRole('status', { name: 'Live-Status' })
    expect(within(summary).getByText('0 von 2 Tablets online')).toBeInTheDocument()
    expect(within(summary).getByText(/2 werden noch abgefragt/)).toBeInTheDocument()
    expect(within(tableRow('Kiosk Frankfurt')).getByText('Wird abgefragt …')).toBeInTheDocument()
    expect(within(tableRow('Kiosk Frankfurt')).getByText(/zuletzt gemeldet 14\.11\.26/)).toBeInTheDocument()
    expect(within(tableRow('Kiosk Viernheim')).getByText('noch nie gemeldet')).toBeInTheDocument()
    expect(screen.queryByText('Offline')).not.toBeInTheDocument()
  })

  it('nennt Einzahl und ein einzelnes abgefragtes Tablet richtig', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(presence([row(3, 'CHECKING')]), [frankfurt])
    renderWithProviders(<DevicesPage />)
    const summary = await screen.findByRole('status', { name: 'Live-Status' })
    expect(within(summary).getByText('0 von 1 Tablet online')).toBeInTheDocument()
    expect(within(summary).getByText(/1 wird noch abgefragt/)).toBeInTheDocument()
  })

  it('zeigt Stempelungen, die am Tablet auf die Übertragung warten, und abgelehnte', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(
      presence([
        row(3, 'ONLINE', { queued_punches: 3, failed_punches: 1 }),
        row(4, 'OFFLINE', { last_seen: '2026-11-14T09:05:00', queued_punches: 1, failed_punches: 0 }),
      ]),
      [frankfurt, viernheim],
    )
    renderWithProviders(<DevicesPage />)

    const online = within(await waitFor(() => tableRow('Kiosk Frankfurt')))
    expect(await online.findByText(/3 Stempelungen warten am Tablet auf die Übertragung/)).toBeInTheDocument()
    expect(online.getByText('davon 1 vom Server abgelehnt – am Tablet prüfen')).toBeInTheDocument()
    const offline = within(tableRow('Kiosk Viernheim'))
    expect(offline.getByText(/Bei der letzten Meldung wartete dort 1 Stempelung auf die Übertragung/)).toBeInTheDocument()
    expect(offline.queryByText(/abgelehnt/)).not.toBeInTheDocument()
  })

  it('ohne wartende Stempelungen kein Hinweis', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(presence([row(3, 'ONLINE')]), [frankfurt])
    renderWithProviders(<DevicesPage />)
    expect(await within(await waitFor(() => tableRow('Kiosk Frankfurt'))).findByText('Online')).toBeInTheDocument()
    expect(screen.queryByText(/Übertragung/)).not.toBeInTheDocument()
  })

  it('kennzeichnet ein schlafendes Tablet außerhalb der Bildschirmzeiten nicht als Störfall', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(presence([row(3, 'OFFLINE', { screen_off: true })]), [frankfurt])
    renderWithProviders(<DevicesPage />)
    const cell = within(await waitFor(() => tableRow('Kiosk Frankfurt')))
    expect(await cell.findByText('Offline – außerhalb der Bildschirmzeiten')).toBeInTheDocument()
    expect(cell.queryByText('Offline')).not.toBeInTheDocument()
  })

  it('fragt alle 5 Sekunden neu ab, solange die Seite offen ist, und hört beim Verlassen auf', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    loginAs({ kind: 'hr', role: 'HR' })
    let state: Row['state'] = 'CHECKING'
    const calls = api(() => presence([row(3, state)]), [frankfurt])
    const view = renderWithProviders(<DevicesPage />)
    expect(await screen.findByText('Wird abgefragt …')).toBeInTheDocument()
    expect(presenceCalls(calls)).toBe(1)

    state = 'ONLINE' // das Tablet hat geantwortet
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PRESENCE_REFETCH_MS)
    })
    expect(await screen.findByText('Online')).toBeInTheDocument()
    expect(presenceCalls(calls)).toBe(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2 * PRESENCE_REFETCH_MS)
    })
    expect(presenceCalls(calls)).toBe(4)

    // Seite verlassen: keine Abfragen mehr – der Server lässt die Tablets nach 30 s wieder ruhen
    view.unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10 * PRESENCE_REFETCH_MS)
    })
    expect(presenceCalls(calls)).toBe(4)
  })

  it('zeigt bei gescheiterter Abfrage einen Hinweis und den letzten Kontakt statt eines falschen Zustands', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(new ApiFailure(500, 'INTERNAL', 'Serverfehler'), [frankfurt])
    renderWithProviders(<DevicesPage />)

    expect(await screen.findByText(/Der Live-Status ist gerade nicht abrufbar/)).toBeInTheDocument()
    const cell = within(tableRow('Kiosk Frankfurt'))
    expect(cell.getByText(/Zuletzt gemeldet: 14\.11\.26/)).toBeInTheDocument()
    expect(cell.queryByText('Online')).not.toBeInTheDocument()
    expect(cell.queryByText('Offline')).not.toBeInTheDocument()
  })

  it('ohne Tablets keine Zusammenfassung', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(presence([]), [])
    renderWithProviders(<DevicesPage />)
    expect(await screen.findByText('Keine Tablets registriert.')).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Live-Status' })).not.toBeInTheDocument()
  })

  it('nur ungekoppelte Einträge: keine Zusammenfassung „0 von 0“', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api(presence([row(5, 'OFFLINE', { last_seen: null })]), [spare])
    renderWithProviders(<DevicesPage />)
    expect(await screen.findByText('Kein Gerät gekoppelt')).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Live-Status' })).not.toBeInTheDocument()
  })
})
