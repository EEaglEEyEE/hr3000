/** Server-Aufrufe des Kiosks: nur echte Verbindungsprobleme dürfen als "offline" gelten
 * (sonst landen abgelehnte Stempelungen in der Warteschlange). */
import { describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, createPunch, deviceLogin, generateIdempotencyKey, getKioskConfig, setupPin } from './api'

function stubFetch(response: Response | Error) {
  const fetchMock = vi.fn(async () => {
    if (response instanceof Error) throw response
    return response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const PUNCH = {
  employee_id: 1,
  punch_type: 'COME' as const,
  timestamp_utc: '2026-10-21T06:00:00.000Z',
  idempotency_key: '7f1f3c1e-2a43-4c55-9d0e-0a1b2c3d4e5f',
}

describe('Server-Aufrufe', () => {
  it('meldet "keine Verbindung", wenn der Server nicht erreichbar ist', async () => {
    stubFetch(new TypeError('Failed to fetch'))
    await expect(createPunch('token', PUNCH)).rejects.toBeInstanceOf(NetworkError)
  })

  it('reicht Fehlercode und Meldung des Servers weiter', async () => {
    stubFetch(new Response(JSON.stringify({ detail: 'PIN falsch.', code: 'PIN_INVALID' }), { status: 401 }))
    const error = await createPunch('token', PUNCH).catch((err: unknown) => err)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, code: 'PIN_INVALID', message: 'PIN falsch.' })
  })

  it('kommt mit Fehlerseiten ohne JSON zurecht (z.B. Proxy 502)', async () => {
    stubFetch(new Response('<html>Bad Gateway</html>', { status: 502 }))
    await expect(createPunch('token', PUNCH)).rejects.toMatchObject({ status: 502, code: undefined, message: 'Unbekannter Fehler.' })
  })

  it('akzeptiert leere Antworten (204)', async () => {
    stubFetch(new Response(null, { status: 204 }))
    await expect(setupPin('token', { employee_id: 1, pin: '1234' })).resolves.toBeUndefined()
  })

  it('sendet Stempelungen mit Token, JSON und Idempotenz-Schlüssel an /api/punches', async () => {
    const fetchMock = stubFetch(new Response(JSON.stringify({ id: 1 }), { status: 201 }))
    await createPunch('geheim', { ...PUNCH, pin: '1234' })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/punches')
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({ Authorization: 'Bearer geheim', 'Content-Type': 'application/json' })
    expect(JSON.parse(String(init.body))).toEqual({ ...PUNCH, pin: '1234' })
  })

  it('meldet sich ohne Authorization-Kopf an und liest die Kiosk-Einstellungen', async () => {
    const fetchMock = stubFetch(new Response(JSON.stringify({ access_token: 'a', errand_buttons: false }), { status: 200 }))
    const login = await deviceLogin('device-token')
    expect(login.errand_buttons).toBe(false)
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.headers).not.toHaveProperty('Authorization')

    stubFetch(new Response(JSON.stringify({ require_pin: true, break_buttons: false }), { status: 200 }))
    await expect(getKioskConfig('a')).resolves.toEqual({ require_pin: true, break_buttons: false })
  })
})

describe('Idempotenz-Schlüssel', () => {
  const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

  it('ist eine gültige, eindeutige UUID v4', () => {
    const keys = new Set(Array.from({ length: 500 }, () => generateIdempotencyKey()))
    expect(keys.size).toBe(500)
    for (const key of keys) expect(key).toMatch(UUID_V4)
  })

  it('funktioniert auch ohne crypto.randomUUID (Tablet per HTTP im WLAN)', () => {
    vi.stubGlobal('crypto', {})
    const keys = new Set(Array.from({ length: 500 }, () => generateIdempotencyKey()))
    expect(keys.size).toBe(500)
    for (const key of keys) expect(key).toMatch(UUID_V4)
  })
})
