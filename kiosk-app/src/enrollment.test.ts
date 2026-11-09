/** Verteilung per MDM: Start-URL lesen und das Gerät mit dem Registrierungsschlüssel einrichten. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, deviceLogin, enrollDevice, type DeviceLoginResponse } from './api'
import { getStoredDeviceToken } from './deviceAuth'
import { enrollFromMdm, enrollmentFromHash } from './enrollment'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, deviceLogin: vi.fn(), enrollDevice: vi.fn() }
})

const login = vi.mocked(deviceLogin)
const enroll = vi.mocked(enrollDevice)
const KEY = 'Ab3_dE-fGhIjKlMnOpQrStUvWxYz0123456789abcde'
const SESSION = { access_token: 'access' } as DeviceLoginResponse

describe('enrollmentFromHash', () => {
  it('liest Schlüssel und Gerätenamen (URL-kodiert)', () => {
    expect(enrollmentFromHash(`#enroll=${KEY}&name=NB%20FRA+01`)).toEqual({ key: KEY, name: 'NB FRA 01' })
    expect(enrollmentFromHash(`#name=NB-01&enroll=${KEY}`)).toEqual({ key: KEY, name: 'NB-01' })
  })

  it('ohne Namen oder mit leerem Namen: name null', () => {
    expect(enrollmentFromHash(`#enroll=${KEY}`)).toEqual({ key: KEY, name: null })
    expect(enrollmentFromHash(`#enroll=${KEY}&name=%20`)).toEqual({ key: KEY, name: null })
  })

  it('nicht ersetzte MDM-Platzhalter zählen als „kein Name“', () => {
    for (const placeholder of ['%devicename%', '%serialnumber%', '{{devicename}}', '%7B%7Bserialnumber%7D%7D', '100%']) {
      expect(enrollmentFromHash(`#enroll=${KEY}&name=${placeholder}`)).toEqual({ key: KEY, name: null })
    }
    expect(enrollmentFromHash(`#enroll=${KEY}&name=HR-FRA-01`)).toEqual({ key: KEY, name: 'HR-FRA-01' })
  })

  it('ignoriert andere und ungültige Fragmente', () => {
    expect(enrollmentFromHash('')).toBeNull()
    expect(enrollmentFromHash('#pair=K7Q4-9XZ2')).toBeNull()
    expect(enrollmentFromHash('#enroll=zu-kurz')).toBeNull()
    expect(enrollmentFromHash(`#enroll=${KEY}<script>`)).toBeNull()
  })
})

describe('enrollFromMdm', () => {
  beforeEach(() => {
    login.mockReset()
    enroll.mockReset()
  })

  it('vorbereitetes Gerät: Token speichern und direkt anmelden', async () => {
    enroll.mockResolvedValue({ status: 'BOUND', device_token: 'tok-bound' })
    login.mockResolvedValue(SESSION)
    expect(await enrollFromMdm({ key: KEY, name: 'NB-01' })).toEqual({ kind: 'ok', session: SESSION })
    expect(enroll).toHaveBeenCalledWith(KEY, 'NB-01')
    expect(login).toHaveBeenCalledWith('tok-bound')
    expect(getStoredDeviceToken()).toBe('tok-bound')
  })

  it('wartet auf Freigabe: Token trotzdem speichern, Prüfcode zeigen', async () => {
    enroll.mockResolvedValue({ status: 'PENDING', device_token: 'tok-pending', verify_code: 'K7Q-4XZ' })
    expect(await enrollFromMdm({ key: KEY, name: null })).toEqual({ kind: 'pending', verifyCode: 'K7Q-4XZ' })
    expect(login).not.toHaveBeenCalled()
    expect(getStoredDeviceToken()).toBe('tok-pending')
  })

  it('ungültiger Schlüssel: Meldung, kein automatischer neuer Versuch', async () => {
    enroll.mockRejectedValue(new ApiError(401, 'ENROLLMENT_KEY_INVALID', 'Registrierungsschlüssel ungültig.'))
    expect(await enrollFromMdm({ key: KEY, name: null })).toEqual({
      kind: 'failed',
      message: 'Registrierungsschlüssel ungültig.',
      retry: false,
    })
  })

  it('Netz, Serverfehler oder zu viele Anfragen: später erneut', async () => {
    for (const err of [new NetworkError(), new ApiError(502, undefined, 'Bad Gateway'), new ApiError(429, 'X', 'Zu viele')]) {
      enroll.mockRejectedValueOnce(err)
      const outcome = await enrollFromMdm({ key: KEY, name: null })
      expect(outcome.kind === 'failed' && outcome.retry).toBe(true)
    }
  })
})
