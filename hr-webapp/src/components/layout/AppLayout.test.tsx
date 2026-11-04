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
  it('zeigt Admins alle Bereiche inklusive Einstellungen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ ...features(), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    for (const label of ['Startseite', 'Mitarbeiter', 'Zu klären', 'Urlaubsanträge', 'Lohn-Export', 'Teams', 'Audit-Log']) {
      expect(within(nav()).getByRole('link', { name: new RegExp(label) })).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: 'Einstellungen' })).toBeInTheDocument()
  })

  it('zeigt Teamleadern nur das Tagesgeschäft', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({ ...features(), ...hrTodoRoutes() })
    renderLayout()
    await screen.findByText('Inhalt')
    expect(within(nav()).getByRole('link', { name: /Zu klären/ })).toBeInTheDocument()
    for (const label of ['Lohn-Export', 'Monatsabschluss', 'Teams', 'Tablets', 'Audit-Log']) {
      expect(within(nav()).queryByRole('link', { name: new RegExp(label) })).not.toBeInTheDocument()
    }
    expect(screen.queryByRole('link', { name: 'Einstellungen' })).not.toBeInTheDocument()
  })

  it('blendet Schichtplanung nur ein, wenn sie aktiviert ist', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ ...features({ shift_planning_enabled: true }), ...hrTodoRoutes() })
    renderLayout()
    expect(await within(nav()).findByRole('link', { name: /Schichtplan-Kalender/ })).toBeInTheDocument()
  })

  it('blendet "Urlaubsanträge" aus, wenn Anträge abgeschaltet und keine offen sind', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ ...features({ absence_requests_enabled: false }), ...hrTodoRoutes() })
    renderLayout()
    await waitFor(() => expect(calls.some((call) => call.path === '/features')).toBe(true))
    await waitFor(() => expect(within(nav()).queryByRole('link', { name: /Urlaubsanträge/ })).not.toBeInTheDocument())
  })

  it('lässt "Urlaubsanträge" stehen, solange alte Anträge offen sind', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    // Schichtplanung an = sichtbares Zeichen, dass die Feature-Schalter geladen sind
    // (vorher zeigt die Leiste "Urlaubsanträge" ohnehin an).
    mockApi({
      ...features({ absence_requests_enabled: false, shift_planning_enabled: true }),
      ...hrTodoRoutes({ pendingAbsences: [{ id: 7 }] }),
    })
    renderLayout()
    await within(nav()).findByRole('link', { name: /Schichtplan-Kalender/ })
    expect(await within(nav()).findByRole('link', { name: /Urlaubsanträge/ })).toBeInTheDocument()
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
