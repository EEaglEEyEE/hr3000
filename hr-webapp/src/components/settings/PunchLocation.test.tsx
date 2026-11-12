/** Standort beim Stempeln (A18): Positionsabfrage nur im Moment des Stempelns, Einstellungen (Schalter, Modus),
 * Kreis je Standort und das Kennzeichen „außerhalb“/„Standort unbekannt“ an der Buchung. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { dashboard, dashboardMe, settings, type DashboardMe } from '../../test/fixtures'
import { currentPosition, MAX_ACCURACY_M, parseGeofence } from '../../lib/geolocation'
import { Dashboard } from '../dashboard/Dashboard'
import { LocationFormDialog } from '../locations/LocationFormDialog'
import { PunchHistoryTab } from '../punches/PunchHistoryTab'
import { LocationsPage } from '../../pages/LocationsPage'
import { SettingsPage } from '../../pages/SettingsPage'

type Success = (position: { coords: { latitude: number; longitude: number; accuracy: number } }) => void
type Failure = (error: { code: number }) => void

const getCurrentPosition = vi.fn()

function geolocationAnswers(coords: { latitude: number; longitude: number; accuracy: number } | 'denied') {
  getCurrentPosition.mockImplementation((success: Success, failure: Failure) => {
    if (coords === 'denied') failure({ code: 1 })
    else success({ coords })
  })
}

beforeEach(() => {
  getCurrentPosition.mockReset()
  Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition }, configurable: true })
})

afterEach(() => {
  Reflect.deleteProperty(navigator, 'geolocation')
})

describe('currentPosition', () => {
  it('liefert Breite, Länge und Genauigkeit und fragt frisch ab (kein Zwischenspeicher)', async () => {
    geolocationAnswers({ latitude: 48.7758, longitude: -9.1829, accuracy: 12.5 })
    await expect(currentPosition()).resolves.toEqual({ latitude: 48.7758, longitude: -9.1829, accuracy_m: 12.5 })
    expect(getCurrentPosition.mock.calls[0][2]).toMatchObject({ maximumAge: 0, enableHighAccuracy: true })
  })

  it('liefert null bei verweigerter Freigabe, unbrauchbarer Genauigkeit oder ohne Standortfunktion', async () => {
    geolocationAnswers('denied')
    await expect(currentPosition()).resolves.toBeNull()
    geolocationAnswers({ latitude: 48, longitude: 9, accuracy: MAX_ACCURACY_M + 1 })
    await expect(currentPosition()).resolves.toBeNull()
    geolocationAnswers({ latitude: Number.NaN, longitude: 9, accuracy: 5 })
    await expect(currentPosition()).resolves.toBeNull()
    Reflect.deleteProperty(navigator, 'geolocation')
    await expect(currentPosition()).resolves.toBeNull()
  })
})

describe('parseGeofence', () => {
  it.each([
    [['', '', ''], null],
    [['48,7758', ' 9.1829 ', '200'], { geo_latitude: 48.7758, geo_longitude: 9.1829, geo_radius_m: 200 }],
    [['-90', '-180', '50'], { geo_latitude: -90, geo_longitude: -180, geo_radius_m: 50 }],
    [['90', '180', '5000'], { geo_latitude: 90, geo_longitude: 180, geo_radius_m: 5000 }],
  ] as const)('übernimmt %j', (input, expected) => {
    expect(parseGeofence(input[0], input[1], input[2])).toEqual(expected)
  })

  it.each([
    [['48.1', '9.2', ''], /Breite, Länge und Radius/],
    [['', '', '200'], /Breite, Länge und Radius/],
    [['90.1', '9.2', '200'], /Breite/],
    [['abc', '9.2', '200'], /Breite/],
    [['48.1', '-180.5', '200'], /Länge/],
    [['48.1', '9.2', '49'], /Radius/],
    [['48.1', '9.2', '5001'], /Radius/],
    [['48.1', '9.2', '100.5'], /Radius/],
  ] as const)('lehnt %j ab', (input, message) => {
    expect(parseGeofence(input[0], input[1], input[2])).toMatch(message)
  })
})

async function renderPunchCard(me: Partial<DashboardMe>, post: unknown) {
  loginAs({ kind: 'employee', employeeId: 5 })
  const calls = mockApi({
    'GET /dashboard': dashboard({ me: dashboardMe({ portal_punching: true, ...me }) }),
    'POST /me/punches': post,
  })
  renderWithProviders(<Dashboard />)
  await screen.findByText('Hallo Erika')
  return calls
}

const PUNCH = { id: 1, employee_id: 5, punch_type: 'COME', source: 'PORTAL', timestamp_utc: '2026-10-21T06:27:00' }

describe('Stempel-Karte mit Standortprüfung', () => {
  it('fragt ohne Standortprüfung nie nach der Position', async () => {
    const calls = await renderPunchCard({ location_check: false }, PUNCH)
    expect(screen.queryByText(/keine Koordinaten/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Kommen' }))
    await screen.findByText(/erfasst\.$/)
    expect(getCurrentPosition).not.toHaveBeenCalled()
    expect(calls.find((call) => call.method === 'POST')?.init.body).toEqual({ punch_type: 'COME' })
  })

  it('schickt die Position nur beim Klick mit und weist auf die Datensparsamkeit hin', async () => {
    geolocationAnswers({ latitude: 48.7758, longitude: 9.1829, accuracy: 20 })
    const calls = await renderPunchCard({ location_check: true }, PUNCH)
    expect(screen.getByText(/keine Koordinaten/)).toBeInTheDocument()
    expect(getCurrentPosition).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Kommen' }))
    await screen.findByText(/erfasst\.$/)
    expect(getCurrentPosition).toHaveBeenCalledTimes(1)
    expect(calls.find((call) => call.method === 'POST')?.init.body).toEqual({
      punch_type: 'COME',
      position: { latitude: 48.7758, longitude: 9.1829, accuracy_m: 20 },
    })
    // Nichts davon landet im Browser-Speicher
    expect(JSON.stringify({ ...localStorage })).not.toContain('48.7758')
  })

  it('stempelt ohne Freigabe ohne Position und zeigt die Ablehnung des Servers', async () => {
    geolocationAnswers('denied')
    const calls = await renderPunchCard(
      { location_check: true, location_check_required: true },
      new ApiFailure(403, 'PUNCH_LOCATION_REQUIRED', 'Stempeln ist nur am Standort möglich. Bitte die Standortfreigabe im Browser erlauben und erneut stempeln.'),
    )
    expect(screen.getByText(/nur am Firmenstandort möglich/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Kommen' }))
    expect(await screen.findByText(/Standortfreigabe im Browser erlauben/)).toBeInTheDocument()
    expect(calls.find((call) => call.method === 'POST')?.init.body).toEqual({ punch_type: 'COME' })
    expect(screen.getByRole('button', { name: 'Kommen' })).toBeEnabled()
  })

  it('sperrt die Knöpfe, solange der Standort ermittelt wird', async () => {
    let answer: Success = () => {}
    getCurrentPosition.mockImplementation((success: Success) => {
      answer = success
    })
    await renderPunchCard({ location_check: true }, PUNCH)
    await userEvent.click(screen.getByRole('button', { name: 'Kommen' }))
    expect(screen.getByText('Standort wird ermittelt…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kommen' })).toBeDisabled()
    answer({ coords: { latitude: 1, longitude: 2, accuracy: 3 } })
    await screen.findByText(/erfasst\.$/)
    expect(screen.queryByText('Standort wird ermittelt…')).not.toBeInTheDocument()
  })
})

describe('Kennzeichen an der Buchung', () => {
  it('zeigt „außerhalb“ und „Standort unbekannt“, aber nichts bei innerhalb oder ungeprüft', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const punch = (id: number, check: string | null, hour: string) => ({
      id, employee_id: 5, location_id: 1, punch_type: 'COME', timestamp_utc: `2026-10-0${id}T${hour}:00:00`, source: 'PORTAL',
      device_id: null, created_by_account_id: 2, corrected: false, correction_reason: null,
      location_check: check, location_check_location_id: check === 'INSIDE' ? 1 : null,
    })
    mockApi({ 'GET /employees/{employee_id}/punches': [punch(1, 'OUTSIDE', '06'), punch(2, 'UNKNOWN', '07'), punch(3, 'INSIDE', '08'), punch(4, null, '09')] })
    renderWithProviders(<PunchHistoryTab employeeId={5} readOnly />)
    const rows = await screen.findAllByRole('row')
    const text = rows.slice(1).map((row) => row.textContent ?? '')
    // Neueste zuerst: 4 (ungeprüft), 3 (innerhalb), 2 (unbekannt), 1 (außerhalb)
    expect(text[0]).not.toMatch(/außerhalb|unbekannt/)
    expect(text[1]).not.toMatch(/außerhalb|unbekannt/)
    expect(text[2]).toContain('Standort unbekannt')
    expect(text[3]).toContain('außerhalb')
    expect(within(rows[4]).getByText('außerhalb')).toHaveAttribute('title', expect.stringMatching(/keine Koordinaten/))
  })
})

function settingsServer(initial = settings(), locations: unknown[] = []) {
  let current = { ...initial }
  const routes = {
    'GET /settings': () => current,
    'PATCH /settings': (init: ApiInit) => {
      current = { ...current, ...(init.body as object) }
      return current
    },
    'GET /locations': locations,
    'GET /absence-types': [],
    'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true },
  }
  return { routes, current: () => current }
}

function renderSettings() {
  return renderWithProviders(
    <Routes>
      <Route path="/einstellungen/:seite?" element={<SettingsPage />} />
    </Routes>,
    { route: '/einstellungen/stempeln' },
  )
}

describe('Einstellungen → Stempeln', () => {
  it('schaltet die Standortprüfung ein (Standard aus) und wählt den Modus', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer(settings(), [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin', geo_latitude: 48, geo_longitude: 9, geo_radius_m: 200 }])
    const calls = mockApi(server.routes)
    renderSettings()

    const toggle = await screen.findByRole('checkbox', { name: /Standort beim Stempeln prüfen/ })
    expect(toggle).not.toBeChecked()
    expect(screen.queryByRole('radio', { name: /Nur vermerken/ })).not.toBeInTheDocument()
    await userEvent.click(toggle)
    await waitFor(() => expect(server.current().punch_location_check_enabled).toBe(true))

    const record = await screen.findByRole('radio', { name: /Nur vermerken/ })
    expect(record).toBeChecked()
    await userEvent.click(screen.getByRole('radio', { name: /Außerhalb nicht erlauben/ }))
    await waitFor(() => expect(server.current().punch_location_mode).toBe('BLOCK'))
    // Nur das jeweilige Feld (plus die festen „nicht leeren“-Marker der Einstellungen)
    const bodies = calls
      .filter((call) => call.method === 'PATCH')
      .map((call) => Object.fromEntries(Object.entries(call.init.body as object).filter(([key]) => !key.startsWith('clear_'))))
    expect(bodies).toEqual([{ punch_location_check_enabled: true }, { punch_location_mode: 'BLOCK' }])
    expect(screen.queryByText(/Noch kein Standort hat einen Kreis/)).not.toBeInTheDocument()
  })

  it('warnt, solange kein Standort einen Kreis hat', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const server = settingsServer(settings({ punch_location_check_enabled: true }), [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }])
    mockApi(server.routes)
    renderSettings()
    expect(await screen.findByText(/Noch kein Standort hat einen Kreis/)).toBeInTheDocument()
  })
})

const LOCATION = { id: 3, name: 'Zentrale', timezone: 'Europe/Berlin', bundesland: null, geo_latitude: 48.7758, geo_longitude: 9.1829, geo_radius_m: 200 }

describe('Standorte: Kreis pflegen', () => {
  it('zeigt den Radius in der Liste', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /locations': [LOCATION, { ...LOCATION, id: 4, name: 'Lager', geo_latitude: null, geo_longitude: null, geo_radius_m: null }] })
    renderWithProviders(<LocationsPage />)
    const rows = await screen.findAllByRole('row')
    expect(rows[1]).toHaveTextContent('200 m')
    expect(rows[2]).toHaveTextContent('–')
  })

  it('legt einen Standort mit Kreis an (Komma als Dezimaltrenner)', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'POST /locations': { ...LOCATION, id: 9 } })
    renderWithProviders(<LocationFormDialog open onOpenChange={() => {}} />)
    await userEvent.type(screen.getByLabelText('Name'), 'Werk 2')
    await userEvent.type(screen.getByLabelText('Breite'), '48,5')
    await userEvent.type(screen.getByLabelText('Länge'), '-9,25')
    await userEvent.type(screen.getByLabelText('Radius (m)'), '300')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.find((call) => call.method === 'POST')).toBeDefined())
    expect(calls.find((call) => call.method === 'POST')?.init.body).toMatchObject({
      name: 'Werk 2', geo_latitude: 48.5, geo_longitude: -9.25, geo_radius_m: 300,
    })
  })

  it('meldet unvollständige oder ungültige Angaben, ohne zu speichern', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({})
    renderWithProviders(<LocationFormDialog open onOpenChange={() => {}} />)
    await userEvent.type(screen.getByLabelText('Name'), 'Werk 2')
    await userEvent.type(screen.getByLabelText('Breite'), '48.5')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/bitte Breite, Länge und Radius angeben/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Länge'), '9.2')
    await userEvent.type(screen.getByLabelText('Radius (m)'), '20')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/zwischen 50 und 5000/)).toBeInTheDocument()
    expect(calls.filter((call) => call.method === 'POST')).toEqual([])
  })

  it('entfernt den Kreis eines Standorts', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'PATCH /locations/{location_id}': { ...LOCATION, geo_latitude: null, geo_longitude: null, geo_radius_m: null } })
    const onOpenChange = vi.fn()
    renderWithProviders(<LocationFormDialog open onOpenChange={onOpenChange} location={LOCATION as never} />)
    expect(screen.getByLabelText('Breite')).toHaveValue('48.7758')
    await userEvent.click(screen.getByRole('button', { name: 'Kreis entfernen' }))
    expect(screen.getByLabelText('Radius (m)')).toHaveValue('')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(calls.find((call) => call.method === 'PATCH')?.init.body).toMatchObject({ clear_geofence: true })
  })

  it('übernimmt auf Knopfdruck den aktuellen Standort als Mittelpunkt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    geolocationAnswers({ latitude: 48.12345678, longitude: 9.87654321, accuracy: 14.4 })
    mockApi({})
    renderWithProviders(<LocationFormDialog open onOpenChange={() => {}} />)
    expect(getCurrentPosition).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Aktuellen Standort übernehmen' }))
    expect(await screen.findByText(/Genauigkeit ca\. 14 m/)).toBeInTheDocument()
    expect(screen.getByLabelText('Breite')).toHaveValue('48.123457')
    expect(screen.getByLabelText('Länge')).toHaveValue('9.876543')
    expect(screen.getByLabelText('Radius (m)')).toHaveValue('200')
  })

  it('erklärt, wenn der Standort nicht ermittelt werden kann', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    geolocationAnswers('denied')
    mockApi({})
    renderWithProviders(<LocationFormDialog open onOpenChange={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Aktuellen Standort übernehmen' }))
    expect(await screen.findByText(/konnte nicht ermittelt werden/)).toBeInTheDocument()
    expect(screen.getByLabelText('Breite')).toHaveValue('')
  })
})
