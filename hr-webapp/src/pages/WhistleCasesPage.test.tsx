/** Meldestelle („Hinweise“): Liste mit Fristen, Bearbeitung, Löschen; Menü, „Mein Bereich“ und
 * Einstellungen des Hinweisgebersystems. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { dashboard, dashboardMe, hrTodoRoutes, settings } from '../test/fixtures'
import { AppLayout } from '../components/layout/AppLayout'
import { WhistleLayout } from '../components/whistle/WhistleLayout'
import { SelfServicePage } from './SelfServicePage'
import { SettingsPage } from './SettingsPage'
import { WhistleCasesPage } from './WhistleCasesPage'

const SUMMARY = {
  id: 3,
  case_number: 'H-ABCDEFGH',
  category: 'CORRUPTION',
  status: 'RECEIVED',
  anonymous: true,
  unread: true,
  received_at: '2026-10-01T08:00:00',
  acknowledged_at: null,
  feedback_at: null,
  closed_at: null,
  ack_due: '2026-10-08',
  ack_overdue: true,
  feedback_due: '2027-01-08',
  feedback_overdue: false,
  delete_after: null,
  deletion_due: false,
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...SUMMARY,
    unread: false,
    description: 'Rechnungen werden doppelt bezahlt.',
    occurred_when: null,
    occurred_where: 'Buchhaltung',
    contact_name: null,
    contact_email: null,
    closing_note: null,
    messages: [
      { id: 1, kind: 'REPORTER', body: 'Nachtrag der meldenden Person', mark: null, author_label: null, created_at: '2026-10-02T08:00:00' },
      { id: 2, kind: 'NOTE', body: 'Intern: Belege prüfen', mark: null, author_label: 'Olga Ombud', created_at: '2026-10-02T09:00:00' },
    ],
    attachments: [{ id: 9, filename: 'beleg.pdf', content_type: 'application/pdf', size_bytes: 2048, created_at: '2026-10-01T08:01:00' }],
    protocol: [{ action: 'WHISTLE_CASE_VIEWED', actor_label: 'Olga Ombud', detail: 'angesehen', created_at: '2026-10-02T09:00:00' }],
    ...overrides,
  }
}

function renderCases(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/hinweise" element={<WhistleLayout />}>
        <Route index element={<WhistleCasesPage />} />
        <Route path=":caseId" element={<WhistleCasesPage />} />
      </Route>
    </Routes>,
    { route },
  )
}

describe('Hinweise – Liste', () => {
  it('zeigt Vorgänge mit Status, überfälligen Fristen und Markierung „neu“', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({
      'GET /whistle/cases': [
        SUMMARY,
        { ...SUMMARY, id: 4, case_number: 'H-ZZZZZZZZ', status: 'CLOSED', unread: false, ack_overdue: false, delete_after: '2029-10-01', deletion_due: true },
      ],
      'GET /whistle/status': { enabled: true, officer: true },
      'GET /notifications': [],
    })
    renderCases('/hinweise')
    const link = await screen.findByRole('link', { name: 'H-ABCDEFGH' })
    const row = link.closest('tr')!
    expect(within(row).getByText('Eingegangen')).toBeInTheDocument()
    expect(within(row).getByText('Korruption oder Betrug')).toBeInTheDocument()
    expect(within(row).getByText('08.10.2026 (überfällig)')).toHaveClass('text-red-600')
    expect(within(row).getByText('neu')).toBeInTheDocument()
    // Abgeschlossene stehen unter „Abgeschlossen“; zur Löschung fällige sind oben vermerkt
    expect(screen.queryByRole('link', { name: 'H-ZZZZZZZZ' })).not.toBeInTheDocument()
    expect(screen.getByText(/1 abgeschlossener Vorgang ist zur Löschung fällig/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Abgeschlossen' }))
    expect(screen.getByRole('link', { name: 'H-ZZZZZZZZ' })).toBeInTheDocument()
    expect(screen.getByText('01.10.2029 (fällig)')).toBeInTheDocument()
    // Mitarbeiter als Beauftragte:r: schlichter Rahmen mit Weg zurück
    expect(screen.getByRole('link', { name: 'Mein Bereich' })).toBeInTheDocument()
  })

  it('zeigt Nicht-Beauftragten nichts', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /whistle/cases': new ApiFailure(404, 'NOT_FOUND', 'Nicht gefunden.'), ...hrTodoRoutes() })
    renderCases('/hinweise')
    expect(await screen.findByText(/nur für benannte Meldestellen-Beauftragte sichtbar/)).toBeInTheDocument()
  })

  it('zeigt eine leere Liste', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({ 'GET /whistle/cases': [], 'GET /notifications': [] })
    renderCases('/hinweise')
    expect(await screen.findByText('Keine Hinweise.')).toBeInTheDocument()
  })
})

describe('Hinweise – Bearbeitung', () => {
  it('zeigt Inhalt, Verlauf mit interner Notiz, Anhänge und Protokoll', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({ 'GET /whistle/cases/{case_id}': detail(), 'GET /notifications': [] })
    renderCases('/hinweise/3')
    expect(await screen.findByText('Rechnungen werden doppelt bezahlt.')).toBeInTheDocument()
    expect(screen.getByText('Buchhaltung')).toBeInTheDocument()
    expect(screen.getByText('Intern: Belege prüfen')).toBeInTheDocument()
    expect(screen.getByText(/Interne Notiz · Olga Ombud/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /beleg.pdf/ })).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Protokoll' })).getByText(/Olga Ombud: angesehen/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Fristen' })).getByText('08.10.2026 (überfällig)')).toBeInTheDocument()
  })

  it('sendet die Eingangsbestätigung als markierte Nachricht', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const calls = mockApi({
      'GET /whistle/cases/{case_id}': detail(),
      'POST /whistle/cases/{case_id}/messages': (init: ApiInit) =>
        detail({
          status: 'IN_REVIEW',
          acknowledged_at: '2026-10-03T08:00:00',
          ack_overdue: false,
          messages: [
            ...detail().messages,
            { id: 3, kind: 'OFFICE', body: (init.body as { body: string }).body, mark: 'ACKNOWLEDGEMENT', author_label: 'Olga Ombud', created_at: '2026-10-03T08:00:00' },
          ],
        }),
      'GET /whistle/cases': [],
      'GET /notifications': [],
    })
    renderCases('/hinweise/3')
    await userEvent.type(await screen.findByLabelText('Text'), 'Ihre Meldung ist eingegangen.')
    await userEvent.click(screen.getByRole('button', { name: 'Als Eingangsbestätigung senden' }))
    await waitFor(() => expect(screen.getByText('Ihre Meldung ist eingegangen.')).toBeInTheDocument())
    const post = calls.find((call) => call.method === 'POST')!
    expect(post.init.params?.path).toEqual({ case_id: 3 })
    expect(post.init.body).toEqual({ kind: 'MESSAGE', body: 'Ihre Meldung ist eingegangen.', mark: 'ACKNOWLEDGEMENT' })
    // Danach gibt es keinen Knopf für eine zweite Bestätigung
    expect(screen.queryByRole('button', { name: 'Als Eingangsbestätigung senden' })).not.toBeInTheDocument()
  })

  it('speichert eine interne Notiz ohne Markierung', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const calls = mockApi({
      'GET /whistle/cases/{case_id}': detail(),
      'POST /whistle/cases/{case_id}/messages': detail(),
      'GET /whistle/cases': [],
      'GET /notifications': [],
    })
    renderCases('/hinweise/3')
    await userEvent.click(await screen.findByLabelText('Interne Notiz'))
    expect(screen.queryByRole('button', { name: 'Als Rückmeldung senden' })).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Text'), 'Zeugen befragen')
    await userEvent.click(screen.getByRole('button', { name: 'Notiz speichern' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')!.init.body).toEqual({ kind: 'NOTE', body: 'Zeugen befragen', mark: null })
  })

  it('schließt nur mit Abschlussvermerk ab', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const calls = mockApi({
      'GET /whistle/cases/{case_id}': detail(),
      'PATCH /whistle/cases/{case_id}': (init: ApiInit) =>
        detail({ status: 'CLOSED', closing_note: (init.body as { closing_note: string }).closing_note, delete_after: '2029-10-05' }),
      'GET /whistle/cases': [],
      'GET /notifications': [],
    })
    renderCases('/hinweise/3')
    await userEvent.selectOptions(await screen.findByLabelText('Status'), 'CLOSED')
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Abschlussvermerk'), 'Verdacht bestätigt.')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Fristen' })).getByText('05.10.2029')).toBeInTheDocument())
    expect(calls.find((call) => call.method === 'PATCH')!.init.body).toEqual({ status: 'CLOSED', closing_note: 'Verdacht bestätigt.' })
    // Abgeschlossen: kein Eingabefeld mehr für Nachrichten
    expect(screen.queryByLabelText('Text')).not.toBeInTheDocument()
  })

  it('löscht einen fälligen Vorgang erst nach Rückfrage', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const calls = mockApi({
      'GET /whistle/cases/{case_id}': detail({ status: 'CLOSED', closing_note: 'Fertig.', delete_after: '2026-10-01', deletion_due: true }),
      'DELETE /whistle/cases/{case_id}': null,
      'GET /whistle/cases': [],
      'GET /notifications': [],
    })
    renderCases('/hinweise/3')
    await userEvent.click(await screen.findByRole('button', { name: 'Vorgang löschen' }))
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Endgültig löschen' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'DELETE')).toBe(true))
    expect(await screen.findByText('Keine Hinweise.')).toBeInTheDocument()
  })

  it('bietet das Löschen vor dem Löschdatum nicht an', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({ 'GET /whistle/cases/{case_id}': detail({ status: 'CLOSED', delete_after: '2029-10-01' }), 'GET /notifications': [] })
    renderCases('/hinweise/3')
    await screen.findByText('Rechnungen werden doppelt bezahlt.')
    expect(screen.queryByRole('button', { name: 'Vorgang löschen' })).not.toBeInTheDocument()
  })

  it('zeigt für unbekannte oder fremde Vorgänge nur „nicht verfügbar“', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({ 'GET /whistle/cases/{case_id}': new ApiFailure(404, 'NOT_FOUND', 'Nicht gefunden.'), 'GET /notifications': [] })
    renderCases('/hinweise/99')
    expect(await screen.findByText('Dieser Hinweis ist nicht verfügbar.')).toBeInTheDocument()
  })
})

describe('Hinweisgebersystem – Menü und „Mein Bereich“', () => {
  function features(whistle = true) {
    return {
      'GET /features': {
        shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true,
        whistleblowing_enabled: whistle,
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

  it('zeigt den Menüpunkt „Hinweise“ nur Beauftragten', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ ...features(), ...hrTodoRoutes(), 'GET /whistle/status': { enabled: true, officer: true } })
    renderLayout()
    expect(await screen.findByRole('link', { name: /Hinweise/ })).toHaveAttribute('href', '/hinweise')
  })

  it('fragt den Status bei ausgeschaltetem Hinweisgebersystem gar nicht ab', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({ ...features(false), ...hrTodoRoutes(), 'GET /whistle/status': { enabled: true, officer: true } })
    renderLayout()
    await screen.findByText('Inhalt')
    await waitFor(() => expect(calls.some((call) => call.path === '/features')).toBe(true))
    await waitFor(() => expect(screen.getByRole('link', { name: /Mitarbeiter/ })).toBeInTheDocument())
    expect(calls.filter((call) => call.path === '/whistle/status')).toHaveLength(0)
    expect(screen.queryByRole('link', { name: /Hinweise/ })).not.toBeInTheDocument()
  })

  it('verbirgt den Menüpunkt für Admins, die nicht benannt sind', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ ...features(), ...hrTodoRoutes(), 'GET /whistle/status': { enabled: true, officer: false } })
    renderLayout()
    await screen.findByText('Inhalt')
    await waitFor(() => expect(screen.getByRole('link', { name: /Mitarbeiter/ })).toBeInTheDocument())
    expect(screen.queryByRole('link', { name: /Hinweise/ })).not.toBeInTheDocument()
  })

  function selfService(status: { enabled: boolean; officer: boolean }) {
    loginAs({ kind: 'employee', employeeId: 5 })
    mockApi({
      'GET /employees/{employee_id}': { id: 5, first_name: 'Erika', last_name: 'Muster' },
      'GET /dashboard': dashboard({ me: dashboardMe() }),
      'GET /absence-types': [],
      'GET /whistle/status': status,
    })
    renderWithProviders(<SelfServicePage />, { route: '/mein-bereich' })
  }

  it('verlinkt in „Mein Bereich“ die Meldeseite und für Beauftragte die Bearbeitung', async () => {
    selfService({ enabled: true, officer: true })
    const report = await screen.findByRole('link', { name: 'Hinweis abgeben' })
    expect(report).toHaveAttribute('href', '/hinweis')
    expect(report).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByRole('link', { name: 'Hinweise bearbeiten' })).toHaveAttribute('href', '/hinweise')
  })

  it('zeigt in „Mein Bereich“ nichts, solange das Hinweisgebersystem aus ist', async () => {
    selfService({ enabled: false, officer: false })
    await screen.findByText('Hallo Erika')
    expect(screen.queryByRole('link', { name: 'Hinweis abgeben' })).not.toBeInTheDocument()
  })

  it('zeigt Mitarbeitern ohne Benennung nur den Link zur Meldeseite', async () => {
    selfService({ enabled: true, officer: false })
    await screen.findByRole('link', { name: 'Hinweis abgeben' })
    expect(screen.queryByRole('link', { name: 'Hinweise bearbeiten' })).not.toBeInTheDocument()
  })
})

describe('Einstellungen → Hinweisgebersystem', () => {
  function server(initialOfficers = { officers: [], candidates: [{ account_id: 7, name: 'Olga Ombud', email: 'olga@example.com' }] }) {
    let current = settings()
    let officers = initialOfficers
    return mockApi({
      'GET /settings': () => current,
      'PATCH /settings': (init: ApiInit) => {
        current = { ...current, ...(init.body as object) }
        return current
      },
      'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true },
      'GET /whistle/officers': () => officers,
      'POST /whistle/officers': (init: ApiInit) => {
        const id = (init.body as { account_id: number }).account_id
        officers = { officers: officers.candidates.filter((c) => c.account_id === id), candidates: officers.candidates.filter((c) => c.account_id !== id) } as typeof officers
        return officers
      },
      'DELETE /whistle/officers/{account_id}': () => {
        officers = { officers: [], candidates: [{ account_id: 7, name: 'Olga Ombud', email: 'olga@example.com' }] }
        return officers
      },
    })
  }

  function renderSettings() {
    return renderWithProviders(
      <Routes>
        <Route path="/einstellungen/:seite?" element={<SettingsPage />} />
      </Routes>,
      { route: '/einstellungen/hinweisgebersystem' },
    )
  }

  it('schaltet das Hinweisgebersystem ein (Standard aus) und zeigt den Link', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = server()
    renderSettings()
    const toggle = await screen.findByRole('checkbox', { name: /Hinweisgebersystem/ })
    expect(toggle).not.toBeChecked()
    expect(screen.getByText(`${window.location.origin}/hinweis`)).toBeInTheDocument()
    expect(await screen.findByText('Noch niemand benannt.')).toBeInTheDocument()
    await userEvent.click(toggle)
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'PATCH').at(-1)?.init.body).toMatchObject({ whistleblowing_enabled: true }),
    )
  })

  it('benennt und beruft Beauftragte ab', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = server()
    renderSettings()
    await userEvent.selectOptions(await screen.findByLabelText('Konto benennen'), '7')
    await userEvent.click(screen.getByRole('button', { name: 'Benennen' }))
    expect(await screen.findByRole('button', { name: 'Abberufen' })).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')!.init.body).toEqual({ account_id: 7 })
    await userEvent.click(screen.getByRole('button', { name: 'Abberufen' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'DELETE')!.init.params?.path).toEqual({ account_id: 7 }))
    expect(await screen.findByText('Noch niemand benannt.')).toBeInTheDocument()
  })

  it('ist für HR nicht sichtbar', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true } })
    renderSettings()
    await screen.findByRole('navigation', { name: 'Bereiche der Einstellungen' })
    expect(screen.queryByRole('link', { name: 'Hinweisgebersystem' })).not.toBeInTheDocument()
  })
})
