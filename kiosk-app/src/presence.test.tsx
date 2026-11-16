/** Meldung an den Server: Abstand kommt vom Server (15 Min. im Ruhezustand, 15 s bei offener Seite
 * „Tablets“), Stand der Offline-Warteschlange, Neuanmeldung bei abgelaufener Sitzung. */
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, deviceLogin, sendHeartbeat, type DeviceLoginResponse } from './api'
import { storeDeviceToken } from './deviceAuth'
import { enqueuePunch, type QueuedPunch } from './offlineQueue'
import { HEARTBEAT_RETRY_MS, IDLE_HEARTBEAT_SECONDS, heartbeatDelayMs, queueState, usePresenceHeartbeat } from './presence'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, sendHeartbeat: vi.fn(), deviceLogin: vi.fn() }
})

const heartbeat = vi.mocked(sendHeartbeat)
const login = vi.mocked(deviceLogin)

function punch(key: string, error?: string): QueuedPunch {
  return { idempotency_key: key, employee_id: 1, employee_name: 'Mia Muster', punch_type: 'COME', timestamp_utc: '2026-11-14T08:00:00', ...(error ? { error } : {}) }
}

function Probe({ token, seconds, onSession }: { token?: string; seconds?: number; onSession: (session: DeviceLoginResponse) => void }) {
  usePresenceHeartbeat(token, seconds, onSession)
  return null
}

/** Lässt laufende Promises (Meldung, Neuanmeldung) durchlaufen, ohne die Uhr weiterzudrehen. */
async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('heartbeatDelayMs', () => {
  it.each([
    [15, 15_000],
    [900, 900_000],
    [5, 5_000],
    [1, 5_000], // nie schneller als alle 5 s
    [0, 5_000],
    [-20, 5_000],
    [3600, 3_600_000],
    [86_400, 3_600_000], // nie seltener als stündlich
  ])('%s s -> %s ms', (seconds, expected) => {
    expect(heartbeatDelayMs(seconds)).toBe(expected)
  })

  it.each([undefined, null, Number.NaN, Number.POSITIVE_INFINITY])('ohne brauchbaren Wert (%s): Ruhezustand', (value) => {
    expect(heartbeatDelayMs(value)).toBe(IDLE_HEARTBEAT_SECONDS * 1000)
  })
})

describe('queueState', () => {
  it('leere Warteschlange', () => {
    expect(queueState()).toEqual({ queued_punches: 0, failed_punches: 0 })
  })

  it('zählt wartende und davon abgelehnte Stempelungen', () => {
    enqueuePunch(punch('a'))
    enqueuePunch(punch('b', 'PIN falsch'))
    enqueuePunch(punch('c'))
    expect(queueState()).toEqual({ queued_punches: 3, failed_punches: 1 })
  })
})

describe('usePresenceHeartbeat', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    heartbeat.mockReset()
    login.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('ohne Anmeldung keine Meldung', async () => {
    render(<Probe onSession={vi.fn()} />)
    await advance(3_600_000)
    expect(heartbeat).not.toHaveBeenCalled()
  })

  it('meldet sich sofort und danach im Abstand, den der Server nennt', async () => {
    heartbeat.mockResolvedValue({ interval_seconds: 900 })
    enqueuePunch(punch('a', 'abgelehnt'))
    render(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    expect(heartbeat).toHaveBeenCalledTimes(1)
    expect(heartbeat).toHaveBeenCalledWith('access', { queued_punches: 1, failed_punches: 1 })

    await advance(899_000)
    expect(heartbeat).toHaveBeenCalledTimes(1)
    await advance(1_000)
    expect(heartbeat).toHaveBeenCalledTimes(2)
  })

  it('wird schneller, sobald die Antwort einen kurzen Abstand nennt, und wieder langsamer', async () => {
    heartbeat
      .mockResolvedValueOnce({ interval_seconds: 15 }) // jemand hat die Seite „Tablets“ geöffnet
      .mockResolvedValueOnce({ interval_seconds: 15 })
      .mockResolvedValue({ interval_seconds: 900 }) // Seite wieder zu
    render(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    await advance(15_000)
    expect(heartbeat).toHaveBeenCalledTimes(2)
    await advance(15_000)
    expect(heartbeat).toHaveBeenCalledTimes(3)
    await advance(60_000)
    expect(heartbeat).toHaveBeenCalledTimes(3)
    await advance(840_000)
    expect(heartbeat).toHaveBeenCalledTimes(4)
  })

  it('meldet sich sofort, wenn die Konfiguration einen neuen Abstand bringt', async () => {
    heartbeat.mockResolvedValue({ interval_seconds: 900 })
    const view = render(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    expect(heartbeat).toHaveBeenCalledTimes(1)

    heartbeat.mockResolvedValue({ interval_seconds: 15 })
    view.rerender(<Probe token="access" seconds={15} onSession={vi.fn()} />)
    await settle()
    expect(heartbeat).toHaveBeenCalledTimes(2) // nicht erst nach 15 Minuten
    await advance(15_000)
    expect(heartbeat).toHaveBeenCalledTimes(3)
  })

  it('gleicher Abstand bei neuer Konfiguration löst keine zusätzliche Meldung aus', async () => {
    heartbeat.mockResolvedValue({ interval_seconds: 900 })
    const view = render(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    view.rerender(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    expect(heartbeat).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['kein Netz', () => new NetworkError()],
    ['Serverfehler', () => new ApiError(503, undefined, 'Wartung')],
  ])('%s: in einer Minute erneut statt erst nach dem Ruheabstand', async (_label, error) => {
    heartbeat.mockRejectedValueOnce(error()).mockResolvedValue({ interval_seconds: 900 })
    render(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    expect(login).not.toHaveBeenCalled()
    await advance(HEARTBEAT_RETRY_MS - 1)
    expect(heartbeat).toHaveBeenCalledTimes(1)
    await advance(1)
    expect(heartbeat).toHaveBeenCalledTimes(2)
  })

  it('abgelaufene Sitzung: meldet sich neu an und übergibt die neue Sitzung', async () => {
    storeDeviceToken('geraet-1')
    const fresh = { access_token: 'neu', heartbeat_seconds: 900 } as DeviceLoginResponse
    heartbeat.mockRejectedValueOnce(new ApiError(401, 'TOKEN_EXPIRED', 'abgelaufen')).mockResolvedValue({ interval_seconds: 900 })
    login.mockResolvedValue(fresh)
    const onSession = vi.fn()
    const view = render(<Probe token="alt" seconds={900} onSession={onSession} />)
    await settle()
    expect(login).toHaveBeenCalledWith('geraet-1')
    expect(onSession).toHaveBeenCalledWith(fresh)

    // Der Aufrufer setzt die neue Sitzung: sofort eine Meldung mit dem neuen Token
    view.rerender(<Probe token="neu" seconds={900} onSession={onSession} />)
    await settle()
    expect(heartbeat).toHaveBeenLastCalledWith('neu', { queued_punches: 0, failed_punches: 0 })
    expect(heartbeat).toHaveBeenCalledTimes(2)
  })

  it('abgelehntes Tablet: höchstens ein Anmeldeversuch pro Minute', async () => {
    storeDeviceToken('geraet-1')
    heartbeat.mockRejectedValue(new ApiError(401, 'TOKEN_INVALID', 'ungültig'))
    login.mockRejectedValue(new ApiError(401, 'INVALID_DEVICE_TOKEN', 'Unbekanntes Gerät.'))
    const onSession = vi.fn()
    render(<Probe token="alt" seconds={15} onSession={onSession} />)
    await settle()
    expect(login).toHaveBeenCalledTimes(1)
    await advance(59_000)
    expect(login).toHaveBeenCalledTimes(1)
    await advance(1_000)
    expect(login).toHaveBeenCalledTimes(2)
    await advance(5 * 60_000)
    expect(login).toHaveBeenCalledTimes(7)
    expect(onSession).not.toHaveBeenCalled()
  })

  it('ohne gespeichertes Token (Tablet zurückgesetzt) keine Neuanmeldung', async () => {
    heartbeat.mockRejectedValue(new ApiError(401, 'TOKEN_INVALID', 'ungültig'))
    const onSession = vi.fn()
    render(<Probe token="alt" seconds={900} onSession={onSession} />)
    await settle()
    expect(login).not.toHaveBeenCalled()
    expect(onSession).not.toHaveBeenCalled()
  })

  it('hört nach der Abmeldung auf', async () => {
    heartbeat.mockResolvedValue({ interval_seconds: 15 })
    const view = render(<Probe token="access" seconds={15} onSession={vi.fn()} />)
    await settle()
    view.rerender(<Probe seconds={15} onSession={vi.fn()} />)
    await advance(600_000)
    expect(heartbeat).toHaveBeenCalledTimes(1)
  })

  it('hört beim Entfernen der Ansicht auf – auch wenn gerade eine Meldung läuft', async () => {
    let finish: (value: { interval_seconds: number }) => void = () => undefined
    heartbeat.mockReturnValue(new Promise((resolve) => (finish = resolve)))
    const view = render(<Probe token="access" seconds={15} onSession={vi.fn()} />)
    view.unmount()
    finish({ interval_seconds: 15 })
    await advance(600_000)
    expect(heartbeat).toHaveBeenCalledTimes(1)
  })
})

describe('Übergabe an die Android-App (Meldung im Standby)', () => {
  const report = vi.fn()

  beforeEach(() => {
    vi.useFakeTimers()
    heartbeat.mockReset()
    login.mockReset()
    report.mockReset()
    localStorage.clear()
    window.HR3000Native = {
      installationId: () => 'and1-Qk3x9vB2mN8pL4tR7wY1zA5cE6fH0jK2sD9gU3iO7qV',
      setKeepAwake: () => undefined,
      appVersion: () => '1.3.0',
      platform: () => 'android',
      reportPresence: report,
    }
  })

  afterEach(() => {
    delete window.HR3000Native
    vi.useRealTimers()
  })

  it('übergibt nach jeder erfolgreichen Meldung Token, Installation und Warteschlange', async () => {
    storeDeviceToken('geraete-token-0123456789')
    heartbeat.mockResolvedValue({ interval_seconds: 900 })
    enqueuePunch(punch('a', 'abgelehnt'))
    enqueuePunch(punch('b'))
    render(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    expect(report).toHaveBeenCalledTimes(1)
    expect(report).toHaveBeenCalledWith('geraete-token-0123456789', 'and1-Qk3x9vB2mN8pL4tR7wY1zA5cE6fH0jK2sD9gU3iO7qV', 'access', 2, 1)
    await advance(900_000)
    expect(report).toHaveBeenCalledTimes(2)
  })

  it('nichts bei gescheiterter Meldung', async () => {
    storeDeviceToken('geraete-token-0123456789')
    heartbeat.mockRejectedValue(new NetworkError())
    render(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    expect(heartbeat).toHaveBeenCalledTimes(1)
    expect(report).not.toHaveBeenCalled()
  })

  it('nichts ohne gespeichertes Geräte-Token', async () => {
    heartbeat.mockResolvedValue({ interval_seconds: 900 })
    render(<Probe token="access" seconds={900} onSession={vi.fn()} />)
    await settle()
    expect(heartbeat).toHaveBeenCalledTimes(1)
    expect(report).not.toHaveBeenCalled()
  })

  it('eine werfende App stört die Meldung nicht', async () => {
    storeDeviceToken('geraete-token-0123456789')
    report.mockImplementation(() => {
      throw new Error('weg')
    })
    heartbeat.mockResolvedValue({ interval_seconds: 60 })
    render(<Probe token="access" seconds={60} onSession={vi.fn()} />)
    await settle()
    await advance(60_000)
    expect(heartbeat).toHaveBeenCalledTimes(2)
  })
})
