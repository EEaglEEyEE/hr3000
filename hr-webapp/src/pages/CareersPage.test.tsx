/** Öffentliche Karriereseite: Liste, Stellenanzeige und Bewerbungsformular ohne Anmeldung. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, mockApi, renderWithProviders } from '../test/utils'
import { CareerJobPage } from './CareerJobPage'
import { CareersPage } from './CareersPage'

const JOB = {
  id: 12,
  slug: 'lagerist-m-w-d',
  title: 'Lagerist (m/w/d)',
  department: 'Logistik',
  location: 'Zentrale',
  employment_type: 'FULL_TIME' as const,
  application_deadline: '2026-12-31',
}

const DETAIL = {
  ...JOB,
  description: 'Wir suchen Verstärkung.\n\n- Waren annehmen\n- Kommissionieren',
  company_name: 'Musterfirma',
  privacy_text: 'Wir verarbeiten Ihre Daten nur für das Bewerbungsverfahren.',
  privacy_url: 'https://example.com/datenschutz',
  max_files: 5,
  max_file_mb: 10,
}

function renderCareers(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/karriere" element={<CareersPage />} />
      <Route path="/karriere/:stelle" element={<CareerJobPage />} />
    </Routes>,
    { route },
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('Karriereseite', () => {
  it('listet die offenen Stellen mit Link zur Anzeige', async () => {
    mockApi({ 'GET /public/careers': { company_name: 'Musterfirma', privacy_text: null, privacy_url: null, jobs: [JOB] } })
    renderCareers('/karriere')
    expect(await screen.findByText('Karriere bei Musterfirma')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Lagerist/ })
    expect(link).toHaveAttribute('href', '/karriere/12-lagerist-m-w-d')
    expect(link).toHaveTextContent('Vollzeit · Logistik · Zentrale')
    expect(link).toHaveTextContent('Bewerbungsschluss: 31.12.2026')
  })

  it('meldet, wenn keine Stellen ausgeschrieben sind', async () => {
    mockApi({ 'GET /public/careers': { company_name: 'Musterfirma', privacy_text: null, privacy_url: null, jobs: [] } })
    renderCareers('/karriere')
    expect(await screen.findByText('Zurzeit sind keine Stellen ausgeschrieben.')).toBeInTheDocument()
  })

  it('zeigt bei ausgeschaltetem Recruiting nur einen Hinweis', async () => {
    mockApi({ 'GET /public/careers': new ApiFailure(404, 'CAREERS_NOT_FOUND', 'Diese Seite gibt es nicht.') })
    renderCareers('/karriere')
    expect(await screen.findByText('Diese Seite gibt es nicht.')).toBeInTheDocument()
  })

  it('zeigt die Anzeige mit Beschreibung als Text und Datenschutzhinweisen', async () => {
    const calls = mockApi({ 'GET /public/careers/jobs/{job_id}': DETAIL })
    renderCareers('/karriere/12-lagerist-m-w-d')
    expect(await screen.findByRole('heading', { name: 'Lagerist (m/w/d)' })).toBeInTheDocument()
    expect(calls[0].init.params?.path).toEqual({ job_id: 12 })
    expect(screen.getByText('Waren annehmen').tagName).toBe('LI')
    expect(screen.getByText(/nur für das Bewerbungsverfahren/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Datenschutzhinweise für Bewerber' })).toHaveAttribute('href', 'https://example.com/datenschutz')
  })

  it('ungültige oder unbekannte Stelle', async () => {
    mockApi({ 'GET /public/careers/jobs/{job_id}': new ApiFailure(404, 'RECRUITING_JOB_NOT_FOUND', 'x') })
    renderCareers('/karriere/99-weg')
    expect(await screen.findByText('Diese Stelle gibt es nicht (mehr).')).toBeInTheDocument()
  })

  it('ungültige Adresse fragt den Server gar nicht', async () => {
    const calls = mockApi({})
    renderCareers('/karriere/kaputt')
    expect(await screen.findByText('Diese Stelle gibt es nicht (mehr).')).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })
})

describe('Bewerbungsformular', () => {
  async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
    await user.type(await screen.findByLabelText('Vorname'), 'Clara')
    await user.type(screen.getByLabelText('Nachname'), 'Kandidat')
    await user.type(screen.getByLabelText('E-Mail'), 'clara@example.com')
  }

  it('sendet die Bewerbung mit Dateien ohne Token und bedankt sich', async () => {
    localStorage.setItem('hr3000.access_token', 'sollte-nicht-mitgehen')
    mockApi({ 'GET /public/careers/jobs/{job_id}': DETAIL })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{"received":true}', { status: 201 }))
    const user = userEvent.setup()
    renderCareers('/karriere/12')
    await fillRequired(user)
    await user.type(screen.getByLabelText('Telefon (optional)'), '+49 30 123')
    await user.type(screen.getByLabelText('Anschreiben (optional)'), 'Hallo!')
    const cv = new File(['%PDF-1.4'], 'lebenslauf.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByLabelText('Lebenslauf (PDF, PNG oder JPEG)'), cv)
    await user.upload(screen.getByLabelText('Weitere Anhänge (z. B. Zeugnisse)'), [
      new File(['x'], 'zeugnis.png', { type: 'image/png' }),
    ])
    await user.click(screen.getByLabelText('Ich habe die Datenschutzhinweise zur Kenntnis genommen.'))
    await user.click(screen.getByLabelText('Meine Bewerbung darf auch für künftige Stellen aufbewahrt werden.'))
    await user.click(screen.getByRole('button', { name: 'Bewerbung absenden' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Vielen Dank für Ihre Bewerbung!')
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe('/api/public/careers/jobs/12/applications')
    expect((init as RequestInit).headers).toBeUndefined()
    const form = (init as RequestInit).body as FormData
    expect(form.get('first_name')).toBe('Clara')
    expect(form.get('email')).toBe('clara@example.com')
    expect(form.get('phone')).toBe('+49 30 123')
    expect(form.get('cover_letter')).toBe('Hallo!')
    expect(form.get('privacy_acknowledged')).toBe('true')
    expect(form.get('talent_pool')).toBe('true')
    expect(form.get('website')).toBeNull()
    expect((form.get('cv') as File).name).toBe('lebenslauf.pdf')
    expect((form.getAll('attachments') as File[]).map((f) => f.name)).toEqual(['zeugnis.png'])
  })

  it('das Honeypot-Feld ist für Menschen versteckt', async () => {
    mockApi({ 'GET /public/careers/jobs/{job_id}': DETAIL })
    renderCareers('/karriere/12')
    const honeypot = await screen.findByLabelText('Website')
    expect(honeypot).toHaveAttribute('tabindex', '-1')
    expect(honeypot.closest('[aria-hidden="true"]')).not.toBeNull()
  })

  it('ohne Häkchen bei den Datenschutzhinweisen wird nichts gesendet', async () => {
    mockApi({ 'GET /public/careers/jobs/{job_id}': DETAIL })
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const user = userEvent.setup()
    renderCareers('/karriere/12')
    await fillRequired(user)
    await user.click(screen.getByRole('button', { name: 'Bewerbung absenden' }))
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('prüft Anzahl und Größe der Dateien vor dem Senden', async () => {
    mockApi({ 'GET /public/careers/jobs/{job_id}': { ...DETAIL, max_files: 1, max_file_mb: 1 } })
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const user = userEvent.setup()
    renderCareers('/karriere/12')
    await fillRequired(user)
    await user.click(screen.getByLabelText('Ich habe die Datenschutzhinweise zur Kenntnis genommen.'))
    await user.upload(screen.getByLabelText('Weitere Anhänge (z. B. Zeugnisse)'), [
      new File(['a'], 'a.pdf', { type: 'application/pdf' }),
      new File(['b'], 'b.pdf', { type: 'application/pdf' }),
    ])
    await user.click(screen.getByRole('button', { name: 'Bewerbung absenden' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Höchstens 1 Dateien.')
    const big = new File([new Uint8Array(1024 * 1024 + 1)], 'gross.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByLabelText('Weitere Anhänge (z. B. Zeugnisse)'), [big])
    await user.click(screen.getByRole('button', { name: 'Bewerbung absenden' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('höchstens 1 MB')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it.each([
    [429, 'TOO_MANY_APPLICATIONS', 'Zu viele Bewerbungen'],
    [422, 'VALIDATION', 'Bitte die Eingaben prüfen'],
    [400, 'UNSUPPORTED_FILE_TYPE', 'Erlaubt sind nur PDF, PNG und JPEG.'],
  ])('zeigt Fehler %i verständlich an', async (status, code, text) => {
    mockApi({ 'GET /public/careers/jobs/{job_id}': DETAIL })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ code, detail: 'Erlaubt sind nur PDF, PNG und JPEG.' }), { status }),
    )
    const user = userEvent.setup()
    renderCareers('/karriere/12')
    await fillRequired(user)
    await user.click(screen.getByLabelText('Ich habe die Datenschutzhinweise zur Kenntnis genommen.'))
    await user.click(screen.getByRole('button', { name: 'Bewerbung absenden' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(text))
  })
})
