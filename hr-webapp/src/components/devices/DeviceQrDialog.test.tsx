/** QR-Code zum Einrichten eines Tablets: Die Kiosk-Adresse kommt vom Server (kiosk.firma.hr3000.de),
 * nicht aus dem Hostnamen im Browser. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import QRCode from 'qrcode'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Device } from '../../api/queries/devices'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { DeviceQrDialog } from './DeviceQrDialog'

const device: Device = {
  id: 7,
  location_id: 1,
  name: 'Tablet Eingang',
  last_seen: null,
}

function qrContents(spy: { mock: { calls: unknown[][] } }): string[] {
  return spy.mock.calls.map((call: unknown[]) => String(call[0]))
}

describe('Tablet einrichten (QR-Code)', () => {
  afterEach(() => vi.restoreAllMocks())

  it('kodiert die Kiosk-Adresse aus der Server-Antwort mit dem einmaligen Kopplungscode, nie ein Token', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const qr = vi.spyOn(QRCode, 'toString')
    mockApi({
      'POST /devices/{device_id}/pairing-code': {
        code: 'ABCD-EFGH',
        expires_at: '2026-11-04T12:00:00',
        kiosk_url: 'https://kiosk.lassner.hr3000.de/',
      },
    })
    renderWithProviders(<DeviceQrDialog device={device} onClose={() => {}} />)
    expect(await screen.findByText('ABCD-EFGH')).toBeInTheDocument()
    await waitFor(() => expect(qrContents(qr)).toContain('https://kiosk.lassner.hr3000.de/#pair=ABCD-EFGH'))
    // Nie eine im Browser zusammengebaute Adresse (altes Schema firma.kiosk.…).
    expect(qrContents(qr).every((content) => !content.includes('.kiosk.'))).toBe(true)
    expect(qrContents(qr).every((content) => !content.includes('token='))).toBe(true)
  })

  it('kodiert nur den Code, wenn der Server keine Kiosk-Adresse kennt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const qr = vi.spyOn(QRCode, 'toString')
    mockApi({
      'POST /devices/{device_id}/pairing-code': { code: 'ABCD-EFGH', expires_at: '2026-11-04T12:00:00', kiosk_url: null },
    })
    renderWithProviders(<DeviceQrDialog device={device} onClose={() => {}} />)
    await waitFor(() => expect(qrContents(qr)).toEqual(['ABCD-EFGH']))
  })

  it('zeigt keinen QR-Code, wenn der Kopplungscode scheitert', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const qr = vi.spyOn(QRCode, 'toString')
    mockApi({ 'POST /devices/{device_id}/pairing-code': new ApiFailure(500, 'BOOM', 'kaputt') })
    renderWithProviders(<DeviceQrDialog device={device} onClose={() => {}} />)
    await waitFor(() => expect(screen.queryByText('ABCD-EFGH')).not.toBeInTheDocument())
    expect(qrContents(qr)).toEqual([])
  })

  function pairingBodies(calls: ApiCall[]) {
    return calls.filter((call) => call.method === 'POST' && call.path === '/devices/{device_id}/pairing-code').map((call) => call.init.body)
  }
  const code = { code: 'ABCD-EFGH', expires_at: '2026-11-04T12:00:00', kiosk_url: null }

  it('erzeugt für ein freies Tablet den Code sofort, ohne Tausch', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'POST /devices/{device_id}/pairing-code': code })
    renderWithProviders(<DeviceQrDialog device={device} onClose={() => {}} />)
    expect(await screen.findByText('ABCD-EFGH')).toBeInTheDocument()
    expect(pairingBodies(calls)).toEqual([{ replace_bound: false }])
    expect(screen.queryByText(/schon mit einem Gerät verbunden/)).not.toBeInTheDocument()
  })

  it('fragt bei einem verbundenen Tablet erst nach, bevor ein anderes Gerät es übernehmen kann', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'POST /devices/{device_id}/pairing-code': code })
    renderWithProviders(<DeviceQrDialog device={{ ...device, bound_at: '2026-11-09T08:37:28' }} onClose={() => {}} />)
    expect(await screen.findByText(/Dieses Tablet ist schon mit einem Gerät verbunden \(seit/)).toBeInTheDocument()
    expect(screen.getByText(/Für ein\s+zusätzliches Tablet bitte „Neues Tablet“ anlegen/)).toBeInTheDocument()
    expect(pairingBodies(calls)).toEqual([]) // noch kein Code
    expect(screen.queryByText('ABCD-EFGH')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Gerät tauschen – QR-Code erzeugen' }))
    expect(await screen.findByText('ABCD-EFGH')).toBeInTheDocument()
    expect(pairingBodies(calls)).toEqual([{ replace_bound: true }])
  })

  it('erzeugt nach „Abbrechen“ keinen Code', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'POST /devices/{device_id}/pairing-code': code })
    const onClose = vi.fn()
    renderWithProviders(<DeviceQrDialog device={{ ...device, bound_at: '2026-11-09T08:37:28' }} onClose={onClose} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Abbrechen' }))
    expect(onClose).toHaveBeenCalled()
    expect(pairingBodies(calls)).toEqual([])
  })

  it('fragt auch nach, wenn erst der Server meldet, dass das Tablet inzwischen verbunden ist', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    let first = true
    const calls = mockApi({
      'POST /devices/{device_id}/pairing-code': () => {
        if (first) {
          first = false
          return new ApiFailure(409, 'DEVICE_BOUND', 'Das Tablet ist schon mit einem Gerät verbunden.')
        }
        return code
      },
    })
    renderWithProviders(<DeviceQrDialog device={device} onClose={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Gerät tauschen – QR-Code erzeugen' }))
    expect(await screen.findByText('ABCD-EFGH')).toBeInTheDocument()
    expect(pairingBodies(calls)).toEqual([{ replace_bound: false }, { replace_bound: true }])
  })
})
