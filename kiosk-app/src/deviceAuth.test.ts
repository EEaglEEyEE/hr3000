/** Anmeldung beim Start: Das gespeicherte Geräte-Token darf bei einer Störung nie verloren gehen –
 * sonst muss das Tablet von Hand neu gekoppelt werden (Vorfall 06.11.2026). */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, deviceLogin, type DeviceLoginResponse } from './api'
import { getStoredDeviceToken, resumeSession, storeDeviceToken } from './deviceAuth'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, deviceLogin: vi.fn() }
})

const login = vi.mocked(deviceLogin)
const SESSION = { access_token: 'access' } as DeviceLoginResponse

describe('resumeSession', () => {
  beforeEach(() => {
    login.mockReset()
  })

  it('ohne gespeichertes Token: nicht eingerichtet, kein Server-Aufruf', async () => {
    expect(await resumeSession()).toEqual({ kind: 'none' })
    expect(login).not.toHaveBeenCalled()
  })

  it('meldet sich mit dem gespeicherten Token an', async () => {
    storeDeviceToken('geraet-1')
    login.mockResolvedValue(SESSION)
    expect(await resumeSession()).toEqual({ kind: 'ok', session: SESSION })
    expect(login).toHaveBeenCalledWith('geraet-1')
  })

  it('behält das Token, wenn der Server es ablehnt', async () => {
    storeDeviceToken('geraet-1')
    login.mockRejectedValue(new ApiError(401, 'INVALID_DEVICE_TOKEN', 'Unbekanntes Gerät.'))
    expect(await resumeSession()).toEqual({ kind: 'rejected' })
    expect(getStoredDeviceToken()).toBe('geraet-1')
  })

  it('per MDM registriert und noch nicht freigegeben: wartet mit Prüfcode, Token bleibt', async () => {
    storeDeviceToken('tok')
    login.mockRejectedValue(
      new ApiError(403, 'DEVICE_PENDING', 'Dieses Gerät wartet auf Freigabe in der HR-Webapp unter „Tablets“. Prüfcode: K7Q-4XZ'),
    )
    expect(await resumeSession()).toEqual({ kind: 'pending', verifyCode: 'K7Q-4XZ' })
    expect(getStoredDeviceToken()).toBe('tok')
  })

  it('erkennt, wenn ein anderes Gerät den Zugang belegt (kein automatischer neuer Versuch)', async () => {
    storeDeviceToken('tok')
    login.mockRejectedValue(new ApiError(401, 'DEVICE_IN_USE', 'Anderes Gerät.'))
    expect(await resumeSession()).toEqual({ kind: 'in_use' })
    expect(getStoredDeviceToken()).toBe('tok')
  })

  it('behält das Token ohne Netz und bei Serverfehlern', async () => {
    storeDeviceToken('geraet-1')
    for (const err of [new NetworkError(), new ApiError(502, undefined, 'Bad Gateway')]) {
      login.mockRejectedValueOnce(err)
      expect(await resumeSession()).toEqual({ kind: 'unreachable' })
      expect(getStoredDeviceToken()).toBe('geraet-1')
    }
  })

  it('klappt nach einer Störung der nächste Versuch wieder', async () => {
    storeDeviceToken('geraet-1')
    login.mockRejectedValueOnce(new ApiError(401, 'INVALID_DEVICE_TOKEN', 'Unbekanntes Gerät.'))
    login.mockResolvedValueOnce(SESSION)
    expect((await resumeSession()).kind).toBe('rejected')
    expect(await resumeSession()).toEqual({ kind: 'ok', session: SESSION })
  })
})
