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
  device_token: 'tok/en+123',
  last_seen: null,
}

function qrContents(spy: { mock: { calls: unknown[][] } }): string[] {
  return spy.mock.calls.map((call: unknown[]) => String(call[0]))
}

describe('Tablet einrichten (QR-Code)', () => {
  afterEach(() => vi.restoreAllMocks())

  it('kodiert die Kiosk-Adresse aus der Server-Antwort samt Token', async () => {
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
    await waitFor(() => expect(qrContents(qr)).toContain('https://kiosk.lassner.hr3000.de/#token=tok%2Fen%2B123'))
    // Nie eine im Browser zusammengebaute Adresse (altes Schema firma.kiosk.…).
    expect(qrContents(qr).every((content) => !content.includes('.kiosk.'))).toBe(true)
  })

  it('kodiert nur das Token, wenn der Server keine Adresse kennt oder der Code scheitert', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const qr = vi.spyOn(QRCode, 'toString')
    mockApi({ 'POST /devices/{device_id}/pairing-code': new ApiFailure(500, 'BOOM', 'kaputt') })
    renderWithProviders(<DeviceQrDialog device={device} onClose={() => {}} />)
    await waitFor(() => expect(qrContents(qr)).toEqual(['tok/en+123']))
  })
})
