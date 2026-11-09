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
  last_seen_at: '2026-11-08T09:00:00', conflict_device_name: null,
}

function api(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /locations': [{ id: 1, name: 'Frankfurt', timezone: 'Europe/Berlin' }],
    'GET /devices': [device],
    'GET /devices/enrollments': [enrollment],
    'GET /devices/enrollment-keys': [],
    'POST /devices/enrollments/{enrollment_id}/approve': (init: ApiInit) => ({ ...device, id: 4, ...(init.body as object) }),
    'DELETE /devices/enrollments/{enrollment_id}': undefined,
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

  it('erzeugt einen Schlüssel und zeigt die Start-URL nur einmal', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api({ 'GET /devices/enrollments': [] })
    renderWithProviders(<DevicesPage />)
    expect(await screen.findByText('MDM: NB-FRA-01')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Neue Geräte' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Verteilung per MDM' }))
    expect(await screen.findByText('kein Schlüssel')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Gültigkeit neuer Schlüssel'), 'none')
    await userEvent.click(screen.getByRole('button', { name: 'Schlüssel erzeugen' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path === '/devices/enrollment-keys')?.init.body).toEqual({
        location_id: 1,
        valid_days: null,
      }),
    )
    const dialog = await screen.findByRole('dialog')
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
