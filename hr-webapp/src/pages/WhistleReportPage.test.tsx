/** Öffentliche Meldeseite /hinweis: ohne Anmeldung, nie mit Anmelde-Token, Zugangscode nur einmal. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, renderWithProviders } from '../test/utils'
import { WhistleReportPage } from './WhistleReportPage'

const INFO = { company_name: 'Musterfirma', accepting_reports: true, max_attachment_bytes: 10 * 1024 * 1024, max_attachments: 10 }
const CASE = {
  case_number: 'H-ABCDEFGH',
  category: 'SAFETY',
  status: 'IN_REVIEW',
  description: 'Notausgang ist dauerhaft verstellt.',
  received_at: '2026-11-02T08:00:00',
  acknowledged_at: '2026-11-03T09:00:00',
  messages: [{ from_office: true, body: 'Danke, wir prüfen das.', created_at: '2026-11-03T09:00:00', mark: 'ACKNOWLEDGEMENT' }],
  attachments: [{ filename: 'foto.jpg', size_bytes: 2048, created_at: '2026-11-02T08:01:00' }],
}

type Handler = (url: string, init: RequestInit) => { status: number; body: unknown }
interface Sent {
  url: string
  init: RequestInit
}

function server(handlers: Record<string, Handler | { status: number; body: unknown }>) {
  const sent: Sent[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input)
    sent.push({ url, init })
    const key = `${init.method ?? 'GET'} ${url.replace('/api/public/whistle', '')}`
    const handler = handlers[key]
    if (url === '/api/branding') return new Response(JSON.stringify({ tenant_name: null, logo_data_url: null }), { status: 200 })
    if (!handler) return new Response(JSON.stringify({ detail: 'Nicht gefunden.', code: 'NOT_FOUND' }), { status: 404 })
    const { status, body } = typeof handler === 'function' ? handler(url, init) : handler
    return new Response(JSON.stringify(body), { status })
  })
  vi.stubGlobal('fetch', fetchMock)
  return sent
}

function whistleRequests(sent: Sent[]) {
  return sent.filter((request) => request.url.startsWith('/api/public/whistle'))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Meldeseite', () => {
  it('zeigt einen Hinweis, wenn die Firma kein Hinweisgebersystem hat', async () => {
    server({})
    renderWithProviders(<WhistleReportPage />, { route: '/hinweis' })
    expect(await screen.findByText(/kein Hinweisgebersystem eingerichtet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hinweis absenden' })).not.toBeInTheDocument()
  })

  it('nimmt ohne Beauftragte keine Meldungen an', async () => {
    server({ 'GET /info': { status: 200, body: { ...INFO, accepting_reports: false } } })
    renderWithProviders(<WhistleReportPage />)
    expect(await screen.findByText(/keine neuen Hinweise abgegeben werden/)).toBeInTheDocument()
  })

  it('sendet eine anonyme Meldung ohne Anmelde-Token und zeigt Vorgangsnummer und Code', async () => {
    loginAs({ kind: 'employee', employeeId: 7 }) // auch angemeldet: kein Token an die Meldeseite
    const sent = server({
      'GET /info': { status: 200, body: INFO },
      'POST /reports': { status: 201, body: { case_number: 'H-ABCDEFGH', access_code: 'ABCDE-FGHJK-LMNPQ-RSTUV' } },
    })
    renderWithProviders(<WhistleReportPage />)
    expect(await screen.findByText(/Dateien können Metadaten enthalten/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Musterfirma/ })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Kategorie'), 'SAFETY')
    await userEvent.type(screen.getByLabelText('Beschreibung'), 'Notausgang ist dauerhaft verstellt.')
    await userEvent.type(screen.getByLabelText('Ort (freiwillig)'), 'Halle 2')
    await userEvent.click(screen.getByRole('button', { name: 'Hinweis absenden' }))

    expect(await screen.findByText('H-ABCDEFGH')).toBeInTheDocument()
    expect(screen.getByText('ABCDE-FGHJK-LMNPQ-RSTUV')).toBeInTheDocument()
    expect(screen.getByText(/nur dieses eine Mal angezeigt/)).toBeInTheDocument()
    const report = whistleRequests(sent).find((request) => request.url.endsWith('/reports'))!
    expect(JSON.parse(String(report.init.body))).toEqual({
      category: 'SAFETY',
      description: 'Notausgang ist dauerhaft verstellt.',
      occurred_when: null,
      occurred_where: 'Halle 2',
      anonymous: true,
      contact_name: null,
      contact_email: null,
    })
    for (const request of whistleRequests(sent)) {
      expect(JSON.stringify(request.init.headers ?? {})).not.toContain('Authorization')
      expect(request.init.credentials).toBe('omit')
    }
  })

  it('verlangt bei Kontaktangabe Name oder E-Mail und prüft die Beschreibung vorab', async () => {
    const sent = server({ 'GET /info': { status: 200, body: INFO } })
    renderWithProviders(<WhistleReportPage />)
    await userEvent.selectOptions(await screen.findByLabelText('Kategorie'), 'OTHER')
    await userEvent.type(screen.getByLabelText('Beschreibung'), 'kurz')
    await userEvent.click(screen.getByRole('button', { name: 'Hinweis absenden' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('mindestens 10 Zeichen')

    await userEvent.type(screen.getByLabelText('Beschreibung'), ' und jetzt lang genug')
    await userEvent.click(screen.getByLabelText('Mit Kontaktangabe melden'))
    await userEvent.click(screen.getByRole('button', { name: 'Hinweis absenden' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Name oder E-Mail-Adresse')
    expect(whistleRequests(sent).filter((r) => r.init.method === 'POST')).toHaveLength(0)
  })

  it('sendet Kontaktangaben nur, wenn nicht anonym, und lädt gewählte Dateien danach hoch', async () => {
    const sent = server({
      'GET /info': { status: 200, body: INFO },
      'POST /reports': { status: 201, body: { case_number: 'H-ABCDEFGH', access_code: 'ABCDE-FGHJK-LMNPQ-RSTUV' } },
      'POST /attachments': { status: 201, body: CASE },
    })
    renderWithProviders(<WhistleReportPage />)
    await userEvent.selectOptions(await screen.findByLabelText('Kategorie'), 'PRIVACY')
    await userEvent.type(screen.getByLabelText('Beschreibung'), 'Kundendaten liegen offen im Netz.')
    await userEvent.click(screen.getByLabelText('Mit Kontaktangabe melden'))
    await userEvent.type(screen.getByLabelText('E-Mail'), 'hanna@example.com')
    const file = new File(['%PDF-1.4'], 'beleg.pdf', { type: 'application/pdf' })
    await userEvent.upload(screen.getByLabelText('Anhänge (freiwillig)'), file)
    await userEvent.click(screen.getByRole('button', { name: 'Hinweis absenden' }))

    await screen.findByText('H-ABCDEFGH')
    const requests = whistleRequests(sent)
    const report = JSON.parse(String(requests.find((r) => r.url.endsWith('/reports'))!.init.body))
    expect(report).toMatchObject({ anonymous: false, contact_email: 'hanna@example.com', contact_name: null })
    const upload = requests.find((r) => r.url.endsWith('/attachments'))!
    const form = upload.init.body as FormData
    expect(form.get('case_number')).toBe('H-ABCDEFGH')
    expect(form.get('access_code')).toBe('ABCDE-FGHJK-LMNPQ-RSTUV')
    expect((form.get('file') as File).name).toBe('beleg.pdf')
  })

  it('meldet abgelehnte Dateien nach dem Absenden', async () => {
    server({
      'GET /info': { status: 200, body: INFO },
      'POST /reports': { status: 201, body: { case_number: 'H-ABCDEFGH', access_code: 'ABCDE-FGHJK-LMNPQ-RSTUV' } },
      'POST /attachments': { status: 415, body: { detail: 'Erlaubt sind PDF, PNG, JPEG, DOCX und XLSX.', code: 'UNSUPPORTED_FILE_TYPE' } },
    })
    renderWithProviders(<WhistleReportPage />)
    await userEvent.selectOptions(await screen.findByLabelText('Kategorie'), 'OTHER')
    await userEvent.type(screen.getByLabelText('Beschreibung'), 'Ein ausreichend langer Text.')
    await userEvent.upload(screen.getByLabelText('Anhänge (freiwillig)'), new File(['x'], 'bild.pdf'))
    await userEvent.click(screen.getByRole('button', { name: 'Hinweis absenden' }))
    expect(await screen.findByText(/bild.pdf: Erlaubt sind PDF/)).toBeInTheDocument()
    expect(screen.getByText('H-ABCDEFGH')).toBeInTheDocument()
  })

  it('lehnt zu große Dateien schon beim Auswählen ab', async () => {
    server({ 'GET /info': { status: 200, body: { ...INFO, max_attachment_bytes: 3 } } })
    renderWithProviders(<WhistleReportPage />)
    await userEvent.upload(await screen.findByLabelText('Anhänge (freiwillig)'), new File(['12345'], 'gross.pdf'))
    expect(await screen.findByRole('alert')).toHaveTextContent('„gross.pdf“ ist größer')
  })

  it('zeigt die Fehlermeldung des Servers, z. B. bei zu vielen Meldungen', async () => {
    server({
      'GET /info': { status: 200, body: INFO },
      'POST /reports': { status: 429, body: { detail: 'Zu viele Fehlversuche. Bitte später erneut versuchen.', code: 'TOO_MANY_REPORTS' } },
    })
    renderWithProviders(<WhistleReportPage />)
    await userEvent.selectOptions(await screen.findByLabelText('Kategorie'), 'OTHER')
    await userEvent.type(screen.getByLabelText('Beschreibung'), 'Ein ausreichend langer Text.')
    await userEvent.click(screen.getByRole('button', { name: 'Hinweis absenden' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Bitte später erneut versuchen')
  })
})

describe('Stand abfragen', () => {
  async function openStatus(handlers: Parameters<typeof server>[0]) {
    const sent = server({ 'GET /info': { status: 200, body: INFO }, ...handlers })
    renderWithProviders(<WhistleReportPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Stand abfragen' }))
    await userEvent.type(screen.getByLabelText('Vorgangsnummer'), 'H-ABCDEFGH')
    await userEvent.type(screen.getByLabelText('Zugangscode'), 'ABCDE-FGHJK-LMNPQ-RSTUV')
    await userEvent.click(screen.getByRole('button', { name: 'Stand abfragen' }))
    return sent
  }

  it('zeigt Status, Nachrichten der Meldestelle und Anhänge; Zugangsdaten nur im Rumpf', async () => {
    const sent = await openStatus({ 'POST /status': { status: 200, body: CASE } })
    expect(await screen.findByText('In Prüfung')).toBeInTheDocument()
    expect(screen.getByText('Danke, wir prüfen das.')).toBeInTheDocument()
    expect(screen.getByText(/foto.jpg/)).toBeInTheDocument()
    const status = whistleRequests(sent).find((r) => r.url.endsWith('/status'))!
    expect(status.url).toBe('/api/public/whistle/status')
    expect(JSON.parse(String(status.init.body))).toEqual({ case_number: 'H-ABCDEFGH', access_code: 'ABCDE-FGHJK-LMNPQ-RSTUV' })
  })

  it('antwortet der Meldestelle', async () => {
    const sent = await openStatus({
      'POST /status': { status: 200, body: CASE },
      'POST /messages': (_url, init) => {
        const body = JSON.parse(String(init.body))
        return {
          status: 201,
          body: { ...CASE, messages: [...CASE.messages, { from_office: false, body: body.body, created_at: '2026-11-04T10:00:00', mark: null }] },
        }
      },
    })
    await userEvent.type(await screen.findByLabelText('Antwort an die Meldestelle'), 'Es betrifft auch Halle 3.')
    await userEvent.click(screen.getByRole('button', { name: 'Nachricht senden' }))
    expect(await screen.findByText('Es betrifft auch Halle 3.')).toBeInTheDocument()
    const message = whistleRequests(sent).find((r) => r.url.endsWith('/messages'))!
    expect(JSON.parse(String(message.init.body))).toMatchObject({ case_number: 'H-ABCDEFGH', body: 'Es betrifft auch Halle 3.' })
    await waitFor(() => expect(screen.getByLabelText('Antwort an die Meldestelle')).toHaveValue(''))
  })

  it('reicht eine Datei nach', async () => {
    const sent = await openStatus({
      'POST /status': { status: 200, body: CASE },
      'POST /attachments': {
        status: 201,
        body: { ...CASE, attachments: [...CASE.attachments, { filename: 'nachtrag.pdf', size_bytes: 4096, created_at: '2026-11-04T10:00:00' }] },
      },
    })
    await userEvent.upload(await screen.findByLabelText('Datei nachreichen'), new File(['%PDF'], 'nachtrag.pdf'))
    expect(await screen.findByText(/nachtrag.pdf/)).toBeInTheDocument()
    expect(whistleRequests(sent).some((r) => r.url.endsWith('/attachments'))).toBe(true)
  })

  it('zeigt bei falschem Code dieselbe neutrale Meldung', async () => {
    await openStatus({
      'POST /status': { status: 401, body: { detail: 'Vorgangsnummer oder Zugangscode stimmen nicht.', code: 'WHISTLE_ACCESS_INVALID' } },
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('Vorgangsnummer oder Zugangscode stimmen nicht.')
  })

  it('bietet bei abgeschlossenen Vorgängen keine Antwort mehr an', async () => {
    await openStatus({ 'POST /status': { status: 200, body: { ...CASE, status: 'CLOSED' } } })
    expect(await screen.findByText('Abgeschlossen')).toBeInTheDocument()
    expect(screen.queryByLabelText('Antwort an die Meldestelle')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Datei nachreichen')).not.toBeInTheDocument()
  })
})
