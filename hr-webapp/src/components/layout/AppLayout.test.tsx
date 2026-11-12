import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { hrTodoRoutes, openDay } from '../../test/fixtures'
import { AppLayout } from './AppLayout'

function features(overrides: Record<string, unknown> = {}) {
  return {
    'GET /features': {
      shift_planning_enabled: false,
      absence_requests_enabled: true,
      default_auto_break: true,
      default_show_birthday: true,
      ...overrides,
    },
  }
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

function nav() {
  return screen.getByRole('navigation')
}

describe('Seitenleiste', () => {
  it('zeigt Admins das Tagesgeschäft und die Abrechnung, Konfiguration unter Einstellungen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ ...features(), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    for (const label of ['Startseite', 'Mitarbeiter', 'Zu klären', 'Monatsabschluss', 'Lohn-Export', 'On- & Offboarding']) {
      expect(within(nav()).getByRole('link', { name: new RegExp(label) })).toBeInTheDocument()
    }
    // Standorte, Abteilungen, Feiertage, Tablets, Pausenregeln … stehen jetzt in den Einstellungen (Teams gibt es nicht mehr).
    for (const label of ['Teams', 'Audit-Protokoll', 'Feiertagskalender', 'Tablets', 'Pausenregeln', 'Standorte', 'Lohnarten', 'Zuschläge']) {
      expect(within(nav()).queryByRole('link', { name: new RegExp(label) })).not.toBeInTheDocument()
    }
    expect(within(nav()).getAllByRole('link').length).toBeLessThanOrEqual(10)
    expect(screen.getByRole('link', { name: 'Einstellungen' })).toBeInTheDocument()
  })

  it('zeigt Führungskräften nur das Tagesgeschäft', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({ ...features(), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    expect(within(nav()).getByRole('link', { name: /Zu klären/ })).toBeInTheDocument()
    for (const label of ['Lohn-Export', 'Monatsabschluss', 'Teams', 'Tablets', 'Audit-Protokoll']) {
      expect(within(nav()).queryByRole('link', { name: new RegExp(label) })).not.toBeInTheDocument()
    }
    expect(screen.queryByRole('link', { name: 'Einstellungen' })).not.toBeInTheDocument()
  })

  it('zeigt Führungskräften „Analysen“ nur bei eingeschalteten eigenen Berichten', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({ ...features({ custom_reports_enabled: true }), ...hrTodoRoutes() })
    renderLayout()
    expect(await within(nav()).findByRole('link', { name: /Analysen/ })).toBeInTheDocument()
    expect(within(nav()).queryByRole('link', { name: /Lohn-Export/ })).not.toBeInTheDocument()
  })

  it('blendet „Analysen“ für Führungskräfte ohne eigene Berichte aus', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({ ...features({ custom_reports_enabled: false }), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    await waitFor(() => expect(within(nav()).getByRole('link', { name: /Zu klären/ })).toBeInTheDocument())
    expect(within(nav()).queryByRole('link', { name: /Analysen/ })).not.toBeInTheDocument()
  })

  it('blendet Schichtplanung nur ein, wenn sie aktiviert ist', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ ...features({ shift_planning_enabled: true }), ...hrTodoRoutes() })
    renderLayout()
    expect(await within(nav()).findByRole('link', { name: /Schichtplan-Kalender/ })).toBeInTheDocument()
  })

  it('hat keinen eigenen Menüpunkt „Urlaubsanträge“ mehr – offene Anträge zählen bei „Zu klären“', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({ ...features(), ...hrTodoRoutes({ pendingAbsences: [{ id: 7 }, { id: 8 }] }) })
    renderLayout()
    const link = within(nav()).getByRole('link', { name: /Zu klären/ })
    await waitFor(() => expect(within(link).getByTitle('2 offen')).toHaveTextContent('2'))
    expect(within(nav()).queryByRole('link', { name: /Urlaubsanträge/ })).not.toBeInTheDocument()
  })

  it('zeigt die Anzahl offener Punkte rot an "Zu klären" (offene Tage + Grenzen + Korrekturen)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      ...features(),
      ...hrTodoRoutes({
        openDays: [openDay(1, '2026-10-19'), openDay(2, '2026-10-20')],
        corrections: [{ id: 1 }],
        caps: [{ employee_id: 3, first_name: 'A', last_name: 'Z', cap_minutes: 600, actual_minutes: 700, exceeded: true }],
      }),
    })
    renderLayout()
    const link = within(nav()).getByRole('link', { name: /Zu klären/ })
    await waitFor(() => expect(within(link).getByTitle('4 offen')).toHaveTextContent('4'))
  })

  it('kürzt große Zahlen auf 99+', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const many = Array.from({ length: 120 }, (_, index) => openDay(index, '2026-10-20'))
    mockApi({ ...features(), ...hrTodoRoutes({ openDays: many }) })
    renderLayout()
    const link = within(nav()).getByRole('link', { name: /Zu klären/ })
    await waitFor(() => expect(within(link).getByTitle('120 offen')).toHaveTextContent('99+'))
  })

  it('zeigt Teamleadern keine Korrekturanträge in der Zahl (die entscheidet nur HR)', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    const calls = mockApi({ ...features(), ...hrTodoRoutes({ openDays: [openDay(1, '2026-10-19')], corrections: [{ id: 1 }, { id: 2 }] }) })
    renderLayout()
    const link = within(nav()).getByRole('link', { name: /Zu klären/ })
    await waitFor(() => expect(within(link).getByTitle('1 offen')).toHaveTextContent('1'))
    expect(calls.some((call) => call.path === '/punch-correction-requests')).toBe(false)
  })

  it('merkt sich das Einklappen pro Browser', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ ...features(), ...hrTodoRoutes() })
    renderLayout()
    await userEvent.click(screen.getByTitle('Menü einklappen'))
    expect(localStorage.getItem('hr3000.sidebar_collapsed')).toBe('1')
    expect(screen.getByTitle('Menü ausklappen')).toBeInTheDocument()
  })

  it('zeigt "Mein Bereich" nur für Logins mit eigenem Mitarbeiter', async () => {
    loginAs({ kind: 'employee', employeeId: 5, hrRole: 'ADMIN' })
    mockApi({ ...features(), ...hrTodoRoutes() })
    const { unmount } = renderLayout()
    expect(await screen.findByRole('link', { name: 'Mein Bereich' })).toBeInTheDocument()
    unmount()
    localStorage.clear()

    loginAs({ kind: 'hr', role: 'ADMIN' })
    renderLayout()
    await screen.findByText('Inhalt')
    expect(screen.queryByRole('link', { name: 'Mein Bereich' })).not.toBeInTheDocument()
  })
})

describe('Berechtigung „Vergütung & Lohn-Export“', () => {
  it('HR sieht den Lohn-Export und die Einstellungen (Lohnarten dort nur mit Freigabe)', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ ...features(), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    expect(within(nav()).getByRole('link', { name: /Lohn-Export/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Einstellungen' })).toBeInTheDocument()
  })
})

describe('Seitenleiste mit eigener Rolle', () => {
  it('Lohnbüro (nur lesen) sieht nur die Lohnbuchhaltung und fragt keine Zähler ab', async () => {
    loginAs({ kind: 'hr', role: 'HR', payroll: true, perms: { PAYROLL: 'VIEW' } })
    const calls = mockApi({ ...features({ payroll_accounting_enabled: true }), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    expect(await within(nav()).findByRole('link', { name: /Lohnbuchhaltung/ })).toBeInTheDocument()
    expect(within(nav()).getAllByRole('link')).toHaveLength(1)
    for (const label of ['Startseite', 'Mitarbeiter', 'Zu klären', 'Monatsabschluss', 'Lohn-Export', 'Anwesenheit']) {
      expect(within(nav()).queryByRole('link', { name: new RegExp(label) })).not.toBeInTheDocument()
    }
    expect(screen.queryByRole('link', { name: 'Einstellungen' })).not.toBeInTheDocument()
    const paths = calls.map((c) => c.path)
    for (const path of ['/timesheet/open-days', '/absences/pending', '/change-requests', '/punch-correction-requests']) {
      expect(paths).not.toContain(path)
    }
  })

  it('Zeiten-Rolle sieht Anwesenheit und Zu klären', async () => {
    loginAs({ kind: 'hr', role: 'HR', perms: { TIME: 'EDIT' } })
    const calls = mockApi({ ...features(), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    expect(within(nav()).getByRole('link', { name: /Anwesenheit/ })).toBeInTheDocument()
    expect(within(nav()).getByRole('link', { name: /Zu klären/ })).toBeInTheDocument()
    expect(within(nav()).queryByRole('link', { name: /Analysen/ })).not.toBeInTheDocument()
    await waitFor(() => expect(calls.map((c) => c.path)).toContain('/timesheet/open-days'))
    expect(calls.map((c) => c.path)).not.toContain('/absences/pending')
  })
})

describe('Menüpunkt Lohnbuchhaltung', () => {
  it('erscheint nur, wenn die Lohnbuchhaltung eingeschaltet ist', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ ...features(), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    expect(within(nav()).queryByRole('link', { name: /Lohnbuchhaltung/ })).not.toBeInTheDocument()
  })

  it('zeigt Admins die Lohnbuchhaltung bei eingeschaltetem Schalter', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ ...features({ payroll_accounting_enabled: true }), ...hrTodoRoutes() })
    renderLayout()
    expect(await within(nav()).findByRole('link', { name: /Lohnbuchhaltung/ })).toBeInTheDocument()
  })

  it('nicht für HR ohne „Vergütung & Lohn-Export“', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ ...features({ payroll_accounting_enabled: true }), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    await waitFor(() => expect(within(nav()).getByRole('link', { name: /Lohn-Export/ })).toBeInTheDocument())
    expect(within(nav()).queryByRole('link', { name: /Lohnbuchhaltung/ })).not.toBeInTheDocument()
  })
})
