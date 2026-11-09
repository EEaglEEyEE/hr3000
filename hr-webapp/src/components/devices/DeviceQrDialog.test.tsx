/** QR-Code zum Einrichten eines Tablets: Die Kiosk-Adresse kommt vom Server (kiosk.firma.hr3000.de),
 * nicht aus dem Hostnamen im Browser. */
import { screen, waitFor } from '@testing-library/react'
import QRCode from 'qrcode'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Device } from '../../api/queries/devices'
import { ApiFailure, loginAs, mockApi, renderWithProviders } from '../../test/utils'
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
})
