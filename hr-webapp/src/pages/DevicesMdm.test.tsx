/** Tablets per MDM verteilen: Registrierungsschlüssel, Freigabe neuer Geräte, Gerätename im MDM. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { DevicesPage } from './DevicesPage'

const KEY = 'Ab3_dE-fGhIjKlMnOpQrStUvWxYz0123456789abcde'
const device = {
  id: 3, location_id: 1, name: 'Eingang', last_seen: '2026-11-08T08:00:00', bound_at: '2026-11-01T08:00:00',
  rejected_at: null, theme: null, screen_hours_mode: null, screen_on_from: null, screen_on_until: null, mdm_name: 'NB-FRA-01',
}
const enrollment = {
  id: 9, location_id: 1, reported_name: 'NB-FRA-07', verify_code: 'K7Q-4XZ', created_at: '2026-11-08T09:00:00',
  last_seen_at: '2026-11-08T09:00:00', conflict_device_name: null, active: true,
  client: 'Chrome 157 auf Android', client_ip: '203.0.113.7',
}
const orphan = {
  ...enrollment, id: 11, reported_name: null, verify_code: 'BK8-47R', created_at: '2026-11-08T07:57:00',
  last_seen_at: '2026-11-08T07:58:00', active: false, client: 'Chrome 157 auf Linux', client_ip: '198.51.100.20',
}

function api(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /locations': [{ id: 1, name: 'Frankfurt', timezone: 'Europe/Berlin' }],
    'GET /devices': [device],
    'GET /devices/enrollments': [enrollment],
    'GET /devices/enrollment-keys': [],
    'POST /devices/enrollments/{enrollment_id}/approve': (init: ApiInit) => ({ ...device, id: 4, ...(init.body as object) }),
    'DELETE /devices/enrollments/{enrollment_id}': undefined,
    'POST /devices/enrollments/remove-inactive': { removed: 1 },
    'POST /devices/enrollment-keys': {
      location_id: 1, created_at: '2026-11-08T09:00:00', expires_at: '2026-12-08T09:00:00', last_used_at: null,
      key: KEY, enroll_url: `https://kiosk.firma.hr3000.de/#enroll=${KEY}`,
    },
    'POST /devices': (init: ApiInit) => ({ ...device, id: 5, ...(init.body as object) }),
    ...overrides,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Tablets per MDM', () => {
  it('zeigt wartende Geräte mit Prüfcode und gibt sie als neues Tablet frei', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api()
    renderWithProviders(<DevicesPage />)
    const pending = await screen.findByRole('region', { name: 'Neue Geräte' })
    expect(within(pending).getByText(/K7Q-4XZ/)).toBeInTheDocument()
    expect(within(pending).getByText('Neue Geräte warten auf Freigabe (1)')).toBeInTheDocument()

    await userEvent.click(within(pending).getByRole('button', { name: 'Freigeben' }))
    const name = await screen.findByLabelText('Name des Tablets')
    expect(name).toHaveValue('NB-FRA-07')
    await userEvent.clear(name)
    await userEvent.type(name, 'Kasse 2')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Freigeben' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path.endsWith('/approve'))?.init).toMatchObject({
        params: { path: { enrollment_id: 9 } },
        body: { name: 'Kasse 2' },
      }),
    )
  })

  it('kann ein vorhandenes Tablet ersetzen und warnt bei Namensgleichheit', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api({ 'GET /devices/enrollments': [{ ...enrollment, conflict_device_name: 'Eingang' }] })
    renderWithProviders(<DevicesPage />)
    expect(await screen.findByText(/Das Tablet „Eingang“ mit diesem Gerätenamen ist bereits in Benutzung/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Freigeben' }))
    await userEvent.click(await screen.findByLabelText(/Vorhandenes Tablet ersetzen/))
    expect(screen.getByLabelText('Tablet')).toHaveValue('3')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Freigeben' }))
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('/approve'))?.init.body).toEqual({ device_id: 3 }),
    )
  })

  it('lehnt nach Rückfrage ab', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<DevicesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Ablehnen' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/devices/enrollments/{enrollment_id}')).toBe(true))
  })

  it('zeigt Herkunft und „wartet gerade“ und trennt Anfragen ab, die sich nicht mehr melden', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api({ 'GET /devices/enrollments': [orphan, enrollment] })
    renderWithProviders(<DevicesPage />)
    const pending = await screen.findByRole('region', { name: 'Neue Geräte' })
    // Gezählt werden nur Geräte, die gerade warten
    expect(within(pending).getByText('Neue Geräte warten auf Freigabe (1)')).toBeInTheDocument()
    expect(within(pending).getByText('wartet gerade')).toBeInTheDocument()
    expect(within(pending).getByText('Chrome 157 auf Android · IP-Adresse 203.0.113.7')).toBeInTheDocument()

    const inactive = within(pending).getByRole('group', { name: 'Nicht mehr aktive Anfragen' })
    expect(within(inactive).getByText('Meldet sich nicht mehr (1)')).toBeInTheDocument()
    expect(within(inactive).getByText(/BK8-47R/)).toBeInTheDocument()
    expect(within(inactive).getByText(/zuletzt gemeldet/)).toBeInTheDocument()
    expect(within(inactive).getByText('Chrome 157 auf Linux · IP-Adresse 198.51.100.20')).toBeInTheDocument()
    expect(within(inactive).queryByText('wartet gerade')).not.toBeInTheDocument()
    expect(within(inactive).getByText(/verfallen\s+nach 24 Stunden von selbst/)).toBeInTheDocument()
  })

  it('entfernt alle Anfragen, die sich nicht mehr melden, nach Rückfrage', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api({ 'GET /devices/enrollments': [orphan, enrollment] })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true)
    renderWithProviders(<DevicesPage />)
    const button = await screen.findByRole('button', { name: 'Alle entfernen' })
    await userEvent.click(button) // „Abbrechen“ in der Rückfrage: nichts passiert
    expect(calls.some((c) => c.path === '/devices/enrollments/remove-inactive')).toBe(false)
    await userEvent.click(button)
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/devices/enrollments/remove-inactive')).toBe(true))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('1 Anfrage(n) entfernen'))
  })

  it('zeigt ohne wartendes Gerät nur die verwaisten Anfragen und keine Herkunftszeile ohne Angaben', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api({ 'GET /devices/enrollments': [{ ...orphan, client: null, client_ip: null, last_seen_at: null }] })
    renderWithProviders(<DevicesPage />)
    const pending = await screen.findByRole('region', { name: 'Neue Geräte' })
    expect(within(pending).getByText('Neue Geräte warten auf Freigabe (0)')).toBeInTheDocument()
    expect(within(pending).queryByText(/IP-Adresse/)).not.toBeInTheDocument()
    expect(within(pending).queryByText(/zuletzt gemeldet/)).not.toBeInTheDocument()
  })

  it('zeigt ohne verwaiste Anfragen keinen zweiten Abschnitt', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api()
    renderWithProviders(<DevicesPage />)
    await screen.findByRole('region', { name: 'Neue Geräte' })
    expect(screen.queryByRole('group', { name: 'Nicht mehr aktive Anfragen' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Alle entfernen' })).not.toBeInTheDocument()
  })

  it('erzeugt einen Schlüssel und zeigt die Start-URL nur einmal', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api({ 'GET /devices/enrollments': [] })
    renderWithProviders(<DevicesPage />)
    expect(await screen.findByText('MDM: NB-FRA-01')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Neue Geräte' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Verteilung per MDM' }))
    const row = (await screen.findByRole('cell', { name: 'Frankfurt' })).closest('tr') as HTMLElement
    expect(within(row).getByText('kein Schlüssel')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Gültigkeit neuer Schlüssel'), 'none')
    await userEvent.click(within(row).getByRole('button', { name: 'Schlüssel erzeugen' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path === '/devices/enrollment-keys')?.init.body).toEqual({
        location_id: 1,
        valid_days: null,
      }),
    )
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Registrierungsschlüssel für „Frankfurt“')).toBeInTheDocument()
    expect(within(dialog).getByText(`https://kiosk.firma.hr3000.de/#enroll=${KEY}`)).toBeInTheDocument()
    expect(within(dialog).getByText(/Wird nur jetzt angezeigt/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Fertig' }))
    await waitFor(() => expect(screen.queryByText(`https://kiosk.firma.hr3000.de/#enroll=${KEY}`)).not.toBeInTheDocument())
  })

  it('legt ein Tablet mit Gerätenamen im MDM an', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api({ 'GET /devices/enrollments': [] })
    renderWithProviders(<DevicesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Neues Tablet/ }))
    await userEvent.type(await screen.findByLabelText('Name'), 'Lager')
    await userEvent.type(screen.getByLabelText('Gerätename im MDM (optional)'), ' NB-FRA-02 ')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path === '/devices')?.init.body).toEqual({
        name: 'Lager',
        location_id: 1,
        mdm_name: 'NB-FRA-02',
      }),
    )
  })
})

const companyEnrollment = { ...enrollment, id: 12, location_id: null, reported_name: 'Kiosk-HEF', verify_code: 'HEF-123' }
const twoLocations = [
  { id: 1, name: 'Frankfurt', timezone: 'Europe/Berlin' },
  { id: 2, name: 'Viernheim', timezone: 'Europe/Berlin' },
]
const companyKeyCreated = {
  location_id: null, created_at: '2026-11-15T09:00:00', expires_at: '2026-12-15T09:00:00', last_used_at: null,
  key: KEY, enroll_url: `https://kiosk.firma.hr3000.de/#enroll=${KEY}`, kiosk_url: 'https://kiosk.firma.hr3000.de',
}

describe('Firmenschlüssel', () => {
  it('erzeugt den Firmenschlüssel und zeigt die Werte für die App-Konfiguration einzeln', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api({ 'GET /devices/enrollments': [], 'POST /devices/enrollment-keys': companyKeyCreated })
    renderWithProviders(<DevicesPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Verteilung per MDM' }))
    const company = await screen.findByRole('region', { name: 'Firmenschlüssel' })
    expect(within(company).getByText('kein Schlüssel')).toBeInTheDocument()
    expect(within(company).queryByRole('button', { name: 'Sperren' })).not.toBeInTheDocument()
    await userEvent.click(within(company).getByRole('button', { name: 'Schlüssel erzeugen' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path === '/devices/enrollment-keys')?.init.body).toEqual({
        location_id: null,
        valid_days: 30,
      }),
    )
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Firmenschlüssel (alle Standorte)')).toBeInTheDocument()
    const app = within(dialog).getByRole('region', { name: 'Android-App' })
    expect(within(app).getByText('https://kiosk.firma.hr3000.de')).toBeInTheDocument()
    expect(within(app).getByText(KEY)).toBeInTheDocument()
    expect(within(app).getByText('%devicename%')).toBeInTheDocument()
    expect(within(dialog).getByRole('region', { name: 'Web-App' })).toHaveTextContent(`#enroll=${KEY}`)
  })

  it('kopiert einzelne Werte', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api({ 'GET /devices/enrollments': [], 'POST /devices/enrollment-keys': companyKeyCreated })
    const writeText = vi.fn(() => Promise.resolve())
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithProviders(<DevicesPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Verteilung per MDM' }))
    const company = await screen.findByRole('region', { name: 'Firmenschlüssel' })
    await userEvent.click(within(company).getByRole('button', { name: 'Schlüssel erzeugen' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Registrierungsschlüssel (enrollment_key) kopieren' }))
    expect(writeText).toHaveBeenCalledWith(KEY)
    expect(await within(dialog).findByText('Kopiert')).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Kiosk-Adresse (kiosk_url) kopieren' }))
    expect(writeText).toHaveBeenLastCalledWith('https://kiosk.firma.hr3000.de')
  })

  it('erneuert nur nach Rückfrage und sperrt den Firmenschlüssel', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api({
      'GET /devices/enrollments': [],
      'GET /devices/enrollment-keys': [
        { location_id: null, created_at: '2026-11-15T09:00:00', expires_at: null, last_used_at: '2026-11-15T10:00:00' },
      ],
      'DELETE /devices/enrollment-keys/company': undefined,
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true)
    renderWithProviders(<DevicesPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Verteilung per MDM' }))
    const company = await screen.findByRole('region', { name: 'Firmenschlüssel' })
    expect(await within(company).findByText('unbefristet')).toBeInTheDocument()
    expect(within(company).getByText(/zuletzt benutzt/)).toBeInTheDocument()
    // Die Standorttabelle zählt den Firmenschlüssel nicht mit
    const row = screen.getByRole('cell', { name: 'Frankfurt' }).closest('tr') as HTMLElement
    expect(within(row).getByText('kein Schlüssel')).toBeInTheDocument()

    await userEvent.click(within(company).getByRole('button', { name: 'Erneuern' }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Firmenschlüssel erneuern?'))
    expect(calls.some((c) => c.method === 'POST' && c.path === '/devices/enrollment-keys')).toBe(false)

    await userEvent.click(within(company).getByRole('button', { name: 'Sperren' }))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path === '/devices/enrollment-keys/company')).toBe(true),
    )
  })

  it('zeigt Anfragen über den Firmenschlüssel ohne Standort und verlangt beim Freigeben einen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api({ 'GET /locations': twoLocations, 'GET /devices/enrollments': [companyEnrollment] })
    renderWithProviders(<DevicesPage />)
    const pending = await screen.findByRole('region', { name: 'Neue Geräte' })
    expect(within(pending).getByText(/Firmenschlüssel – Standort beim Freigeben wählen/)).toBeInTheDocument()

    await userEvent.click(within(pending).getByRole('button', { name: 'Freigeben' }))
    const dialog = await screen.findByRole('dialog')
    const location = within(dialog).getByLabelText('Standort')
    expect(location).toHaveValue('')
    const submit = within(dialog).getByRole('button', { name: 'Freigeben' })
    expect(submit).toBeDisabled()
    await userEvent.selectOptions(location, '2')
    expect(submit).toBeEnabled()
    await userEvent.click(submit)
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('/approve'))?.init.body).toEqual({ name: 'Kiosk-HEF', location_id: 2 }),
    )
  })

  it('kann über den Firmenschlüssel ein Tablet an jedem Standort ersetzen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const viernheim = { ...device, id: 6, location_id: 2, name: 'Kiosk-Viernheim', mdm_name: null }
    const calls = api({
      'GET /locations': twoLocations,
      'GET /devices': [device, viernheim],
      'GET /devices/enrollments': [companyEnrollment],
    })
    renderWithProviders(<DevicesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben' }))
    await userEvent.click(await screen.findByLabelText(/Vorhandenes Tablet ersetzen/))
    const select = screen.getByLabelText('Tablet')
    expect(within(select).getByRole('option', { name: 'Eingang (Frankfurt)' })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: 'Kiosk-Viernheim (Viernheim)' })).toBeInTheDocument()
    await userEvent.selectOptions(select, '6')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Freigeben' }))
    await waitFor(() => expect(calls.find((c) => c.path.endsWith('/approve'))?.init.body).toEqual({ device_id: 6 }))
  })

  it('Anfrage mit Standort-Schlüssel: Standort ist vorbelegt, ersetzt werden nur dessen Tablets', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const viernheim = { ...device, id: 6, location_id: 2, name: 'Kiosk-Viernheim', mdm_name: null }
    api({ 'GET /locations': twoLocations, 'GET /devices': [device, viernheim] })
    renderWithProviders(<DevicesPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Standort')).toHaveValue('1')
    expect(within(dialog).queryByRole('option', { name: 'Standort wählen …' })).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByLabelText(/Vorhandenes Tablet ersetzen/))
    const options = within(within(dialog).getByLabelText('Tablet')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual(['Eingang'])
  })
})
