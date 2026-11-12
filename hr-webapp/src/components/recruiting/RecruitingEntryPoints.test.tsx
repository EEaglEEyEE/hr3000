/** Einstiege ins Recruiting: Menüpunkt, Reiter in „Mein Bereich“ und Bereich in den Einstellungen. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppLayout } from '../layout/AppLayout'
import { SelfServicePage } from '../../pages/SelfServicePage'
import { SettingsPage } from '../../pages/SettingsPage'
import { dashboard, dashboardMe, hrTodoRoutes, settings } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'

function features(recruiting = true) {
  return {
    'GET /features': {
      shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true,
      recruiting_enabled: recruiting,
    },
  }
}
const FEATURES = features()

function access(overrides: Partial<Record<'enabled' | 'can_manage' | 'member' | 'can_see_salary', boolean>> = {}) {
  return { 'GET /recruiting/access': { enabled: true, can_manage: false, member: false, can_see_salary: false, ...overrides } }
}

function renderLayout() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<p>Inhalt</p>} />
      </Route>
    </Routes>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('Menüpunkt „Recruiting“', () => {
  it.each([
    { label: 'Admin/HR bei eingeschaltetem Recruiting', role: 'ADMIN' as const, data: { can_manage: true }, visible: true },
    { label: 'Führungskraft im Hiring Team', role: 'SUPERVISOR' as const, data: { member: true }, visible: true },
    { label: 'Führungskraft ohne Hiring Team', role: 'SUPERVISOR' as const, data: {}, visible: false },
    { label: 'Admin bei ausgeschaltetem Recruiting', role: 'ADMIN' as const, data: { enabled: false }, visible: false },
  ])('$label → sichtbar = $visible', async ({ role, data, visible }) => {
    loginAs({ kind: 'hr', role })
    mockApi({ ...features(data.enabled !== false), ...hrTodoRoutes(), ...access(data) })
    renderLayout()
    await screen.findByText('Inhalt')
    const nav = screen.getByRole('navigation')
    if (visible) {
      expect(await within(nav).findByRole('link', { name: /Recruiting/ })).toHaveAttribute('href', '/recruiting')
    } else {
      await waitFor(() => expect(within(nav).getByRole('link', { name: /Startseite/ })).toBeInTheDocument())
      expect(within(nav).queryByRole('link', { name: /Recruiting/ })).not.toBeInTheDocument()
    }
  })
})

describe('Menü fragt den Recruiting-Zugang nur bei eingeschaltetem Modul ab', () => {
  it('Schalter aus → keine Anfrage an /recruiting/access', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ ...features(false), ...hrTodoRoutes(), ...access({ can_manage: true }) })
    renderLayout()
    await screen.findByText('Inhalt')
    await waitFor(() => expect(calls.some((call) => call.path === '/features')).toBe(true))
    await waitFor(() => expect(within(screen.getByRole('navigation')).getByRole('link', { name: /Startseite/ })).toBeInTheDocument())
    expect(calls.filter((call) => call.path === '/recruiting/access')).toHaveLength(0)
    expect(screen.queryByRole('link', { name: /Recruiting/ })).not.toBeInTheDocument()
  })

  it('Schalter an → genau eine Anfrage', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ ...features(true), ...hrTodoRoutes(), ...access({ can_manage: true }) })
    renderLayout()
    expect(await screen.findByRole('link', { name: /Recruiting/ })).toBeInTheDocument()
    expect(calls.filter((call) => call.path === '/recruiting/access')).toHaveLength(1)
  })
})

describe('Reiter „Recruiting“ in „Mein Bereich“', () => {
  function routes(member: boolean) {
    return {
      'GET /employees/{employee_id}': { id: 5, first_name: 'Erika', last_name: 'Muster' },
      'GET /dashboard': dashboard({ me: dashboardMe() }),
      ...access({ member }),
      'GET /recruiting/jobs': [],
      'GET /recruiting/applications': [],
    }
  }

  it('erscheint für Konten ohne Verwaltungsrolle im Hiring Team', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi(routes(true))
    renderWithProviders(<SelfServicePage />, { route: '/mein-bereich' })
    await screen.findByText('Hallo Erika')
    await userEvent.click(await screen.findByRole('tab', { name: 'Recruiting' }))
    expect(await screen.findByText('Keine Bewerbungen.')).toBeInTheDocument()
  })

  it('fehlt ohne Hiring Team', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const calls = mockApi(routes(false))
    renderWithProviders(<SelfServicePage />, { route: '/mein-bereich' })
    await screen.findByText('Hallo Erika')
    await waitFor(() => expect(calls.some((c) => c.path === '/recruiting/access')).toBe(true))
    expect(screen.queryByRole('tab', { name: 'Recruiting' })).not.toBeInTheDocument()
  })

  it('fehlt für Konten mit Verwaltungsrolle (die nutzen den Menüpunkt)', async () => {
    loginAs({ kind: 'employee', employeeId: 5, hrRole: 'SUPERVISOR' })
    const calls = mockApi(routes(true))
    renderWithProviders(<SelfServicePage />, { route: '/mein-bereich' })
    await screen.findByText('Hallo Erika')
    expect(screen.queryByRole('tab', { name: 'Recruiting' })).not.toBeInTheDocument()
    expect(calls.some((c) => c.path === '/recruiting/access')).toBe(false)
  })
})

describe('Einstellungen → Recruiting', () => {
  function renderSettings() {
    let current = settings()
    const calls = mockApi({
      'GET /settings': () => current,
      'PATCH /settings': (init: ApiInit) => {
        current = { ...current, ...(init.body as object) }
        return current
      },
      ...FEATURES,
    })
    renderWithProviders(
      <Routes>
        <Route path="/einstellungen/:seite?" element={<SettingsPage />} />
      </Routes>,
      { route: '/einstellungen/recruiting' },
    )
    const patches = () => calls.filter((c) => c.method === 'PATCH').map((c) => c.init.body as Record<string, unknown>)
    return { patches }
  }

  it('schaltet Recruiting ein (Standard aus)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const { patches } = renderSettings()
    const toggle = await screen.findByRole('checkbox', { name: /Recruiting einschalten/ })
    expect(toggle).not.toBeChecked()
    await userEvent.click(toggle)
    await waitFor(() => expect(patches().at(-1)).toMatchObject({ recruiting_enabled: true }))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /Recruiting einschalten/ })).toBeChecked())
  })

  it('speichert Fristen und Datenschutzhinweise', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const { patches } = renderSettings()
    const retention = await screen.findByLabelText('Löschfrist in Monaten')
    expect(retention).toHaveValue(6)
    expect(screen.getByLabelText('Frist im Talentpool in Monaten')).toHaveValue(12)
    await userEvent.clear(retention)
    await userEvent.type(retention, '3')
    await userEvent.click(screen.getByRole('button', { name: 'Fristen speichern' }))
    await waitFor(() => expect(patches().at(-1)).toMatchObject({ recruiting_retention_months: 3, recruiting_talent_pool_months: 12 }))
    expect(await screen.findByText('Gespeichert.')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Datenschutzhinweise (Text)'), 'Hinweise')
    await userEvent.type(screen.getByLabelText('Link zu den Datenschutzhinweisen'), 'https://example.com/ds')
    await userEvent.click(screen.getByRole('button', { name: 'Hinweise speichern' }))
    await waitFor(() =>
      expect(patches().at(-1)).toMatchObject({ recruiting_privacy_text: 'Hinweise', recruiting_privacy_url: 'https://example.com/ds' }),
    )
  })

  it('ist für HR nicht sichtbar (nur Admin)', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ ...FEATURES })
    renderWithProviders(
      <Routes>
        <Route path="/einstellungen/:seite?" element={<SettingsPage />} />
      </Routes>,
      { route: '/einstellungen' },
    )
    const nav = await screen.findByRole('navigation', { name: 'Bereiche der Einstellungen' })
    expect(within(nav).queryByRole('link', { name: 'Recruiting' })).not.toBeInTheDocument()
  })
})
