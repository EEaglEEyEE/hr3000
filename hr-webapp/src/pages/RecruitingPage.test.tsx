/** Recruiting intern: Stellen, Bewerbungen (Spalten/Liste), Detailansicht, Übernahme, Rechte. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { RecruitingPage } from './RecruitingPage'

const ACCESS_ADMIN = { enabled: true, can_manage: true, member: false, can_see_salary: true }
const ACCESS_MEMBER = { enabled: true, can_manage: false, member: true, can_see_salary: false }

const JOB = {
  id: 1,
  title: 'Lagerist',
  slug: 'lagerist',
  department_id: 3,
  department_name: 'Logistik',
  location_id: 4,
  location_name: 'Zentrale',
  employment_type: 'FULL_TIME',
  description: 'Text',
  status: 'PUBLISHED',
  application_deadline: null,
  published_at: '2026-11-01T08:00:00',
  created_at: '2026-11-01T08:00:00',
  public: true,
  members: [{ account_id: 7, name: 'Sam Leitung', email: 'lead@example.com' }],
  application_count: 2,
  open_count: 1,
  deleted_counts: { REJECTED: 3 },
}

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: 10,
    job_id: 1,
    job_title: 'Lagerist',
    first_name: 'Bea',
    last_name: 'Bewerber',
    email: 'bea@example.com',
    stage: 'NEW',
    source: 'CAREER_PAGE',
    talent_pool: false,
    created_at: '2026-11-05T10:00:00',
    closed_at: null,
    delete_on: null,
    average_rating: 4,
    rating_count: 1,
    attachment_count: 1,
    employee_id: null,
    ...overrides,
  }
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...item(),
    phone: '0151 222',
    cover_letter: 'Ich möchte gern bei Ihnen arbeiten.',
    salary_expectation: '45k',
    salary_visible: true,
    rejection_reason: null,
    rejection_note: null,
    privacy_acknowledged_at: '2026-11-05T10:00:00',
    hired_at: null,
    attachments: [{ id: 5, kind: 'CV', original_filename: 'lebenslauf.pdf', content_type: 'application/pdf', size_bytes: 2048, created_at: '2026-11-05T10:00:00' }],
    notes: [{ id: 8, author_account_id: 7, author_name: 'Sam Leitung', body: 'Guter Eindruck', created_at: '2026-11-06T09:00:00', can_delete: true }],
    ratings: [{ account_id: 7, name: 'Sam Leitung', score: 4, comment: 'passt', updated_at: '2026-11-06T09:00:00', mine: false }],
    events: [{ from_stage: null, to_stage: 'NEW', account_name: null, created_at: '2026-11-05T10:00:00' }],
    can_manage: true,
    ...overrides,
  }
}

function routes(access = ACCESS_ADMIN, extra: Record<string, unknown> = {}) {
  return {
    'GET /recruiting/access': access,
    'GET /recruiting/jobs': [JOB],
    'GET /recruiting/applications': [item(), item({ id: 11, first_name: 'Carl', last_name: 'Clever', stage: 'INTERVIEW' })],
    'GET /recruiting/applications/due-for-deletion': [],
    'GET /recruiting/applications/{application_id}': detail(),
    'GET /recruiting/team-candidates': [
      { account_id: 7, name: 'Sam Leitung', email: 'lead@example.com', role: 'SUPERVISOR' },
      { account_id: 9, name: 'Mia Muster', email: 'mia@example.com', role: null },
    ],
    'GET /departments': [{ id: 3, name: 'Logistik' }],
    'GET /locations': [{ id: 4, name: 'Zentrale' }],
    'GET /checklist-templates': [
      { id: 21, kind: 'ONBOARDING', name: 'Onboarding Lager', items: [] },
      { id: 22, kind: 'OFFBOARDING', name: 'Austritt', items: [] },
    ],
    ...extra,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Recruiting', () => {
  it('zeigt Bewerbungen als Spalten nach Phase und als Liste', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(routes())
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    const newColumn = await screen.findByRole('region', { name: 'Neu' })
    expect(within(newColumn).getByText('Bea Bewerber')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Interview' })).getByText('Carl Clever')).toBeInTheDocument()
    for (const stage of ['Sichtung', 'Angebot', 'Eingestellt', 'Abgelehnt', 'Zurückgezogen']) {
      expect(screen.getByRole('region', { name: stage })).toBeInTheDocument()
    }
    await user.click(screen.getByRole('button', { name: /Liste/ }))
    const table = screen.getByRole('table')
    expect(within(table).getAllByText('Karriereseite', { selector: 'td' })).toHaveLength(2)
    expect(within(table).getAllByRole('row')).toHaveLength(3)
  })

  it('filtert nach Stelle', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes())
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await screen.findByText('Bea Bewerber')
    await user.selectOptions(screen.getByLabelText('Stelle'), '1')
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/recruiting/applications' && c.init.params?.query?.job_id === 1)).toBe(true),
    )
  })

  it('zeigt die Stellen mit Status, Zählung und Hiring Team', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(routes())
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('tab', { name: 'Stellen' }))
    expect(await screen.findByText('Veröffentlicht')).toBeInTheDocument()
    expect(screen.getByText('2 (1 offen)')).toBeInTheDocument()
    expect(screen.getByText('Gelöscht: 3 × Abgelehnt')).toBeInTheDocument()
    expect(screen.getByText('Sam Leitung')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Ansehen/ })).toHaveAttribute('href', '/karriere/1-lagerist')
  })

  it('legt eine Stelle mit Hiring Team an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes(ACCESS_ADMIN, { 'POST /recruiting/jobs': (init: ApiInit) => ({ ...JOB, ...(init.body as object), id: 2 }) }))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('tab', { name: 'Stellen' }))
    await user.click(await screen.findByRole('button', { name: /Neue Stelle/ }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Titel'), '  Fahrer  ')
    await user.selectOptions(within(dialog).getByLabelText('Anstellungsart'), 'PART_TIME')
    await user.selectOptions(within(dialog).getByLabelText('Status'), 'PUBLISHED')
    await within(dialog).findByText('Mia Muster')
    await user.click(within(dialog).getByRole('checkbox', { name: /Mia Muster/ }))
    await user.type(within(dialog).getByLabelText('Beschreibung'), 'Wir suchen dich')
    await user.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const body = calls.find((c) => c.method === 'POST' && c.path === '/recruiting/jobs')!.init.body as Record<string, unknown>
    expect(body).toMatchObject({
      title: 'Fahrer', employment_type: 'PART_TIME', status: 'PUBLISHED', member_account_ids: [9], description: 'Wir suchen dich',
    })
  })

  it('zeigt Fehler beim Löschen einer Stelle mit Bewerbungen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockApi(routes(ACCESS_ADMIN, {
      'DELETE /recruiting/jobs/{job_id}': new ApiFailure(409, 'RECRUITING_JOB_IN_USE', 'Bitte die Stelle schließen statt sie zu löschen.'),
    }))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('tab', { name: 'Stellen' }))
    await user.click(await screen.findByRole('button', { name: 'Lagerist löschen' }))
    expect(await screen.findByText('Bitte die Stelle schließen statt sie zu löschen.')).toBeInTheDocument()
  })

  it('öffnet eine Bewerbung mit Daten, Anhängen, Notizen, Bewertungen und Verlauf', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN', payroll: true })
    mockApi(routes())
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('button', { name: /Bea Bewerber/ }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Ich möchte gern bei Ihnen arbeiten.')).toBeInTheDocument()
    expect(within(dialog).getByText('45k')).toBeInTheDocument()
    expect(within(dialog).getByText('lebenslauf.pdf')).toBeInTheDocument()
    expect(within(dialog).getByText('Guter Eindruck')).toBeInTheDocument()
    expect(within(dialog).getByText(/★★★★☆/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Eingang/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Bewerbung jetzt löschen' })).toBeInTheDocument()
  })

  it('ohne Berechtigung keine Gehaltsvorstellung', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes({ ...ACCESS_ADMIN, can_see_salary: false }, {
      'GET /recruiting/applications/{application_id}': detail({ salary_expectation: null, salary_visible: false }),
    }))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('button', { name: /Bea Bewerber/ }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('lebenslauf.pdf')
    expect(within(dialog).queryByText('Gehaltsvorstellung')).not.toBeInTheDocument()
  })

  it('wechselt die Phase – Absage nur mit Grund', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes(ACCESS_ADMIN, {
      'POST /recruiting/applications/{application_id}/stage': (init: ApiInit) => detail(init.body as Record<string, unknown>),
    }))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('button', { name: /Bea Bewerber/ }))
    const dialog = await screen.findByRole('dialog')
    await user.selectOptions(await within(dialog).findByLabelText('Phase'), 'REJECTED')
    await user.selectOptions(within(dialog).getByLabelText('Absagegrund'), 'EXPERIENCE')
    await user.type(within(dialog).getByLabelText('Begründung (optional)'), 'Zu wenig Praxis')
    await user.click(within(dialog).getByRole('button', { name: 'Phase speichern' }))
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/stage'))).toBe(true))
    const body = calls.find((c) => c.path.endsWith('/stage'))!.init.body
    expect(body).toEqual({ stage: 'REJECTED', rejection_reason: 'EXPERIENCE', rejection_note: 'Zu wenig Praxis' })
  })

  it('bewertet und notiert', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    const calls = mockApi(routes(ACCESS_MEMBER, {
      'GET /recruiting/applications/{application_id}': detail({ can_manage: false }),
      'PUT /recruiting/applications/{application_id}/rating': detail({ can_manage: false }),
      'POST /recruiting/applications/{application_id}/notes': detail({ can_manage: false }),
    }))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('button', { name: /Bea Bewerber/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(await within(dialog).findByRole('radio', { name: '5 von 5' }))
    await user.type(within(dialog).getByLabelText('Kommentar zur Bewertung'), 'Top')
    await user.click(within(dialog).getByRole('button', { name: 'Bewertung speichern' }))
    await user.type(within(dialog).getByLabelText('Neue Notiz'), 'Rückruf vereinbart')
    await user.click(within(dialog).getByRole('button', { name: 'Notiz hinzufügen' }))
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/notes'))).toBe(true))
    expect(calls.find((c) => c.path.endsWith('/rating'))!.init.body).toEqual({ score: 5, comment: 'Top' })
    expect(calls.find((c) => c.path.endsWith('/notes'))!.init.body).toEqual({ body: 'Rückruf vereinbart' })
    // Hiring Team ohne Verwaltung: kein Löschen, kein Hochladen, keine Übernahme
    expect(within(dialog).queryByRole('button', { name: 'Bewerbung jetzt löschen' })).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText('Anhang wählen')).not.toBeInTheDocument()
  })

  it('Hiring Team sieht keine Knöpfe zum Anlegen', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi(routes(ACCESS_MEMBER))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await screen.findByText('Bea Bewerber')
    expect(screen.queryByRole('button', { name: /Bewerbung erfassen/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/Zur Löschung fällig/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Stellen' }))
    await screen.findByText('Veröffentlicht')
    expect(screen.queryByRole('button', { name: /Neue Stelle/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Lagerist bearbeiten' })).not.toBeInTheDocument()
  })

  it('zeigt Bewerbungen, die zur Löschung fällig sind', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes(ACCESS_ADMIN, {
      'GET /recruiting/applications/due-for-deletion': [item({ id: 12, first_name: 'Dora', last_name: 'Alt', stage: 'REJECTED', delete_on: '2026-11-20' })],
    }))
    renderWithProviders(<RecruitingPage />)
    expect(await screen.findByText('Zur Löschung fällig (nächste 30 Tage)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dora Alt' }).parentElement).toHaveTextContent('20.11.2026')
  })

  it('erfasst eine Bewerbung manuell und öffnet sie', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes({ ...ACCESS_ADMIN, can_see_salary: false }, {
      'POST /recruiting/applications': detail({ id: 10 }),
    }))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('button', { name: /Bewerbung erfassen/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByLabelText('Gehaltsvorstellung (optional)')).not.toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Vorname'), 'Eva')
    await user.type(within(dialog).getByLabelText('Nachname'), 'Brief')
    await user.type(within(dialog).getByLabelText('E-Mail'), 'eva@example.com')
    await user.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/recruiting/applications')).toBe(true))
    expect(calls.find((c) => c.method === 'POST' && c.path === '/recruiting/applications')!.init.body).toMatchObject({
      job_id: 1, first_name: 'Eva', last_name: 'Brief', email: 'eva@example.com', salary_expectation: null, talent_pool: false,
    })
    expect(await screen.findByText('Ich möchte gern bei Ihnen arbeiten.')).toBeInTheDocument()
  })

  it('übernimmt eine eingestellte Bewerbung als Mitarbeiter', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes(ACCESS_ADMIN, {
      'GET /recruiting/applications/{application_id}': detail({ stage: 'HIRED' }),
      'POST /recruiting/applications/{application_id}/hire': { employee_id: 55, documents_copied: 1, checklist_started: true },
    }))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('button', { name: /Bea Bewerber/ }))
    await user.click(await screen.findByRole('button', { name: 'Als Mitarbeiter übernehmen' }))
    const dialogs = await screen.findAllByRole('dialog')
    const hire = dialogs[dialogs.length - 1]
    await user.type(within(hire).getByLabelText('Personalnummer'), 'P-100')
    await user.type(within(hire).getByLabelText('Anstelldatum'), '2026-12-01')
    await within(hire).findByRole('option', { name: 'Onboarding Lager' })
    expect(within(hire).queryByRole('option', { name: 'Austritt' })).not.toBeInTheDocument()
    await user.selectOptions(within(hire).getByLabelText('Onboarding-Checkliste starten'), '21')
    await user.selectOptions(within(hire).getByLabelText('Dokumentkategorie'), 'CERTIFICATE')
    await user.click(within(hire).getByRole('button', { name: 'Mitarbeiter anlegen' }))
    expect(await screen.findByText(/Mitarbeiter angelegt, 1 Dokument\(e\) in die Personalakte übernommen, Onboarding-Checkliste gestartet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Zum Mitarbeiter' })).toHaveAttribute('href', '/employees/55')
    const body = calls.find((c) => c.path.endsWith('/hire'))!.init.body
    expect(body).toMatchObject({
      employee_number: 'P-100', hire_date: '2026-12-01', first_name: 'Bea', last_name: 'Bewerber',
      private_email: 'bea@example.com', location_id: 4, department_id: 3, attachment_ids: [5],
      document_category: 'CERTIFICATE', checklist_template_id: 21,
    })
  })

  it('bereits übernommen: Phase gesperrt, kein Übernehmen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(routes(ACCESS_ADMIN, { 'GET /recruiting/applications/{application_id}': detail({ stage: 'HIRED', employee_id: 55 }) }))
    const user = userEvent.setup()
    renderWithProviders(<RecruitingPage />)
    await user.click(await screen.findByRole('button', { name: /Bea Bewerber/ }))
    expect(await screen.findByText('Bereits als Mitarbeiter übernommen.')).toBeInTheDocument()
    expect(screen.getByLabelText('Phase')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Als Mitarbeiter übernehmen' })).not.toBeInTheDocument()
  })

  it('Hinweis, wenn Recruiting aus ist oder kein Zugriff besteht', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({ 'GET /recruiting/access': { enabled: false, can_manage: false, member: false, can_see_salary: false } })
    renderWithProviders(<RecruitingPage />)
    expect(await screen.findByText(/Recruiting ist nicht eingeschaltet/)).toBeInTheDocument()
  })
})
