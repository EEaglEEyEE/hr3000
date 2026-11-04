/** Die Mandanten-Schalter in den Einstellungen senden genau das passende Feld und zeigen den
 * gespeicherten Stand; "Mein Bereich" folgt dem Schalter für Abwesenheitsanträge. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { dashboard, dashboardMe, settings } from '../test/fixtures'
import { SelfServicePage } from './SelfServicePage'
import { SettingsPage } from './SettingsPage'

/** Server-Ersatz: PATCH übernimmt die gesendeten Felder, GET liefert den aktuellen Stand. */
function settingsServer(initial = settings()) {
  let current = { ...initial }
  const routes = {
    'GET /settings': () => current,
    'PATCH /settings': (init: ApiInit) => {
      current = { ...current, ...(init.body as object) }
      return current
    },
    'GET /absence-types': [],
    'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true },
  }
  return { routes, current: () => current }
}

function patches(calls: ReturnType<typeof mockApi>) {
  return calls.filter((call) => call.method === 'PATCH' && call.path === '/settings').map((call) => call.init.body as Record<string, unknown>)
}

describe('Einstellungen', () => {
  it('schaltet das Stempeln über den Web-Login im Reiter "Allgemein" ein (Standard aus)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer()
    const calls = mockApi(server.routes)
    renderWithProviders(<SettingsPage />, { route: '/einstellungen' })

    const toggle = await screen.findByRole('checkbox', { name: /Stempeln über den Web-Login/ })
    expect(toggle).not.toBeChecked()
    await userEvent.click(toggle)
    await waitFor(() => expect(patches(calls).at(-1)).toMatchObject({ portal_punching_enabled: true }))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /Stempeln über den Web-Login/ })).toBeChecked())
    // Nur das eine Feld wird geändert (plus die festen "nicht leeren"-Marker).
    const changed = Object.keys(patches(calls).at(-1)!).filter((key) => !key.startsWith('clear_'))
    expect(changed).toEqual(['portal_punching_enabled'])
  })

  it('schaltet Abwesenheitsanträge im Reiter "Abwesenheiten & Urlaub" ab', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer()
    const calls = mockApi(server.routes)
    renderWithProviders(<SettingsPage />, { route: '/einstellungen?bereich=abwesenheiten' })

    const toggle = await screen.findByRole('checkbox', { name: /Mitarbeiter dürfen Urlaub\/Abwesenheiten beantragen/ })
    expect(toggle).toBeChecked()
    await userEvent.click(toggle)
    await waitFor(() => expect(patches(calls).at(-1)).toMatchObject({ absence_requests_enabled: false }))
    expect(server.current().absence_requests_enabled).toBe(false)
  })

  it('schaltet Dienstgang-Buttons im Reiter "Kiosk" ein (Standard aus)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer()
    const calls = mockApi(server.routes)
    renderWithProviders(<SettingsPage />, { route: '/einstellungen?bereich=kiosk' })

    const errand = await screen.findByRole('checkbox', { name: /Dienstgang-Buttons anzeigen/ })
    const breaks = screen.getByRole('checkbox', { name: /Pausen-Buttons anzeigen/ })
    expect(errand).not.toBeChecked()
    expect(breaks).toBeChecked()
    await userEvent.click(errand)
    await waitFor(() => expect(patches(calls).at(-1)).toMatchObject({ kiosk_errand_buttons: true }))
    // Der Web-Login-Schalter liegt nicht mehr im Kiosk-Reiter.
    expect(screen.queryByRole('checkbox', { name: /Stempeln über den Web-Login/ })).not.toBeInTheDocument()
  })

  it('springt bei unbekanntem Reiter in der Adresse auf "Allgemein"', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(settingsServer().routes)
    renderWithProviders(<SettingsPage />, { route: '/einstellungen?bereich=gibtsnicht' })
    expect(await screen.findByRole('checkbox', { name: /Stempeln über den Web-Login/ })).toBeInTheDocument()
  })
})

describe('Mein Bereich → Abwesenheiten', () => {
  function selfServiceRoutes(absenceRequestsEnabled: boolean) {
    return {
      'GET /employees/{employee_id}': { id: 5, first_name: 'Erika', last_name: 'Muster' },
      'GET /dashboard': dashboard({ me: dashboardMe(), absence_requests_enabled: absenceRequestsEnabled }),
      'GET /employees/{employee_id}/absences': [],
      'GET /absence-types': [],
    }
  }

  it.each([
    { enabled: true, visible: true },
    { enabled: false, visible: false },
  ])('Knopf "Neue Abwesenheit" sichtbar = $visible, wenn Anträge erlaubt = $enabled', async ({ enabled, visible }) => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi(selfServiceRoutes(enabled))
    renderWithProviders(<SelfServicePage />, { route: '/mein-bereich' })
    await screen.findByText('Hallo Erika')
    await userEvent.click(screen.getByRole('tab', { name: 'Abwesenheiten' }))
    await screen.findByText('Keine Abwesenheiten erfasst.')
    if (visible) {
      expect(screen.getByRole('button', { name: /Neue Abwesenheit/ })).toBeInTheDocument()
    } else {
      expect(screen.queryByRole('button', { name: /Neue Abwesenheit/ })).not.toBeInTheDocument()
    }
  })
})
