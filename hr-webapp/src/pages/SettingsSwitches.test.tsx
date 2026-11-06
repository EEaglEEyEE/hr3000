/** Die Mandanten-Schalter in den Einstellungen senden genau das passende Feld und zeigen den
 * gespeicherten Stand; "Mein Bereich" folgt dem Schalter für Abwesenheitsanträge. */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
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

/** Einstellungsseite mit Bereich in der Adresse (wie im Router: /einstellungen/:seite?). */
function renderSettings(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/einstellungen/:seite?" element={<SettingsPage />} />
    </Routes>,
    { route },
  )
}

function settingsNav() {
  return screen.getByRole('navigation', { name: 'Bereiche der Einstellungen' })
}

describe('Einstellungen', () => {
  it('schaltet das Stempeln über den Web-Login unter „Stempeln“ ein (Standard aus)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer()
    const calls = mockApi(server.routes)
    renderSettings('/einstellungen/stempeln')

    const toggle = await screen.findByRole('checkbox', { name: /Stempeln über den Web-Login/ })
    expect(toggle).not.toBeChecked()
    await userEvent.click(toggle)
    await waitFor(() => expect(patches(calls).at(-1)).toMatchObject({ portal_punching_enabled: true }))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /Stempeln über den Web-Login/ })).toBeChecked())
    // Nur das eine Feld wird geändert (plus die festen "nicht leeren"-Marker).
    const changed = Object.keys(patches(calls).at(-1)!).filter((key) => !key.startsWith('clear_'))
    expect(changed).toEqual(['portal_punching_enabled'])
  })

  it('schaltet Abwesenheitsanträge unter „Urlaub & Anträge“ ab', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer()
    const calls = mockApi(server.routes)
    renderSettings('/einstellungen/urlaub')

    const toggle = await screen.findByRole('checkbox', { name: /Mitarbeiter dürfen Urlaub\/Abwesenheiten beantragen/ })
    expect(toggle).toBeChecked()
    // Alle Urlaubswerte an einer Stelle
    expect(screen.getByLabelText('Standard-Jahresurlaub (Tage)')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Teilurlaub bei Eintritt oder Austritt/ })).toBeInTheDocument()
    await userEvent.click(toggle)
    await waitFor(() => expect(patches(calls).at(-1)).toMatchObject({ absence_requests_enabled: false }))
    expect(server.current().absence_requests_enabled).toBe(false)
  })

  it('schaltet Dienstgang-Buttons unter „Anzeige am Tablet“ ein (Standard aus)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer()
    const calls = mockApi(server.routes)
    renderSettings('/einstellungen/tablet-anzeige')

    const errand = await screen.findByRole('checkbox', { name: /Dienstgang-Buttons anzeigen/ })
    const breaks = screen.getByRole('checkbox', { name: /Pausen-Buttons anzeigen/ })
    expect(errand).not.toBeChecked()
    expect(breaks).toBeChecked()
    await userEvent.click(errand)
    await waitFor(() => expect(patches(calls).at(-1)).toMatchObject({ kiosk_errand_buttons: true }))
    expect(screen.queryByRole('checkbox', { name: /Stempeln über den Web-Login/ })).not.toBeInTheDocument()
  })

  it('führt alte Reiter-Links (?bereich=) zum passenden Bereich und unbekannte zum ersten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(settingsServer().routes)
    const { unmount } = renderSettings('/einstellungen?bereich=kiosk')
    expect(await screen.findByRole('checkbox', { name: /Stempeln über den Web-Login/ })).toBeInTheDocument()
    unmount()
    renderSettings('/einstellungen/gibtsnicht')
    expect(await screen.findByText('Standard-Bundesland')).toBeInTheDocument()
  })

  it('zeigt einen Speicherfehler an (z. B. abgeschlossene Monate)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer()
    mockApi({
      ...server.routes,
      'PATCH /settings': new ApiFailure(409, 'PERIOD_LOCKED', 'Der Monat 10/2026 ist abgeschlossen.'),
    })
    renderSettings('/einstellungen/arbeitszeit')
    const input = await screen.findByLabelText('Gleitzeitkonten führen ab')
    fireEvent.change(input, { target: { value: '2026-10-01' } })
    expect(await screen.findByText('Der Monat 10/2026 ist abgeschlossen.')).toBeInTheDocument()
  })

  it('zeigt HR nur die eigenen Bereiche, „Lohnarten“ nur mit Freigabe und lädt keine Firmen-Einstellungen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({ 'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true } })
    const { unmount } = renderSettings('/einstellungen')
    const links = await within(settingsNav()).findAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual(['Standorte', 'Teams', 'Feiertage', 'Tablets', 'Audit-Log'])
    expect(calls.some((call) => call.path === '/settings')).toBe(false)
    unmount()

    loginAs({ kind: 'hr', role: 'HR', payroll: true })
    renderSettings('/einstellungen')
    expect(await within(settingsNav()).findByRole('link', { name: 'Lohnarten' })).toBeInTheDocument()
    expect(within(settingsNav()).queryByRole('link', { name: 'Zuschläge' })).not.toBeInTheDocument() // Regeln bleiben Admins
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
