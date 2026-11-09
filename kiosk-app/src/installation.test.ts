/** Gerätebindung: dauerhafte Installations-ID, Chip-Hash, Kopplungs-Links. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { deviceLogin } from './api'
import { tokenFromQr } from './components/QrScanner'
import { installationId, sha256Hex } from './installation'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('Gerätebindung', () => {
  it('erzeugt die Installations-ID einmal und schickt sie bei jeder Anmeldung mit', async () => {
    const id = installationId()
    expect(id.length).toBeGreaterThanOrEqual(30)
    expect(installationId()).toBe(id)
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))
    await deviceLogin('geheim')
    expect(JSON.parse(String((fetchSpy.mock.calls[0][1] as RequestInit).body))).toEqual({ device_token: 'geheim', installation_id: id })
  })

  it('hasht Chips wie der Server (SHA-256 hex)', async () => {
    expect(await sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  })

  it('liest Kopplungscodes und ältere Token-Links aus dem QR-Code', () => {
    expect(tokenFromQr('https://kiosk.demo.hr3000.de/#pair=ABCD-EFGH')).toBe('ABCD-EFGH')
    expect(tokenFromQr('https://kiosk.demo.hr3000.de/#token=alt123')).toBe('alt123')
  })
})
