/** Offline-Warteschlange: Stempelungen ohne Netz dürfen nie verloren gehen, nie doppelt gebucht
 * werden und müssen in der richtigen Reihenfolge ankommen. */
import { describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError } from './api'
import { discardQueuedPunch, enqueuePunch, flushQueue, getQueuedPunches, type QueuedPunch } from './offlineQueue'
import { queued } from './test/fixtures'

function keys(queue: QueuedPunch[] = getQueuedPunches()): string[] {
  return queue.map((punch) => punch.idempotency_key)
}

describe('Offline-Warteschlange', () => {
  it('ist anfangs leer und übersteht kaputte Daten im Speicher', () => {
    expect(getQueuedPunches()).toEqual([])
    localStorage.setItem('kiosk.offline_punch_queue', '{kein json')
    expect(getQueuedPunches()).toEqual([])
    // Danach kann trotzdem wieder eingereiht werden.
    enqueuePunch(queued('a'))
    expect(keys()).toEqual(['a'])
  })

  it('behält die Reihenfolge und übersteht ein Neuladen der Seite (localStorage)', () => {
    enqueuePunch(queued('a'))
    enqueuePunch(queued('b', { punch_type: 'GO' }))
    const raw = JSON.parse(localStorage.getItem('kiosk.offline_punch_queue') ?? '[]') as QueuedPunch[]
    expect(raw.map((p) => p.idempotency_key)).toEqual(['a', 'b'])
  })

  it('sendet alles in Reihenfolge und leert die Schlange', async () => {
    enqueuePunch(queued('a'))
    enqueuePunch(queued('b', { punch_type: 'GO' }))
    const sent: string[] = []
    const onChange = vi.fn()
    await flushQueue(async (punch) => sent.push(punch.idempotency_key), onChange)
    expect(sent).toEqual(['a', 'b'])
    expect(getQueuedPunches()).toEqual([])
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  it('bricht beim Netzwerkfehler ab und behält den Rest in derselben Reihenfolge', async () => {
    enqueuePunch(queued('a'))
    enqueuePunch(queued('b'))
    enqueuePunch(queued('c'))
    const submit = vi.fn(async (punch: QueuedPunch) => {
      if (punch.idempotency_key === 'b') throw new NetworkError()
    })
    await flushQueue(submit, () => {})
    expect(submit).toHaveBeenCalledTimes(2) // c wird nicht vor b gesendet
    expect(keys()).toEqual(['b', 'c'])
    expect(getQueuedPunches().every((p) => !p.error)).toBe(true)
  })

  it('zählt "schon erfasst" (409 PUNCH_DUPLICATE) als Erfolg – keine Doppelbuchung', async () => {
    enqueuePunch(queued('a'))
    enqueuePunch(queued('b'))
    const submit = vi.fn(async (punch: QueuedPunch) => {
      if (punch.idempotency_key === 'a') throw new ApiError(409, 'PUNCH_DUPLICATE', 'Bereits erfasst.')
    })
    await flushQueue(submit, () => {})
    expect(submit).toHaveBeenCalledTimes(2)
    expect(getQueuedPunches()).toEqual([])
  })

  it('markiert abgelehnte Einträge mit der Meldung, ohne die folgenden zu blockieren', async () => {
    enqueuePunch(queued('a'))
    enqueuePunch(queued('b'))
    await flushQueue(async (punch) => {
      if (punch.idempotency_key === 'a') throw new ApiError(401, 'PIN_INVALID', 'PIN falsch.')
    }, () => {})
    expect(getQueuedPunches()).toEqual([{ ...queued('a'), error: 'PIN falsch.' }])
  })

  it('behandelt abgelehnte Tablet-Anmeldung und Serverfehler wie Netzwerkfehler (kein Fehler-Vermerk)', async () => {
    for (const err of [
      new ApiError(401, 'INVALID_DEVICE_TOKEN', 'Unbekanntes Gerät.'),
      new ApiError(401, 'TOKEN_INVALID', 'Ungültiges Token.'),
      new ApiError(503, undefined, 'Service Unavailable'),
    ]) {
      localStorage.clear()
      enqueuePunch(queued('a'))
      enqueuePunch(queued('b'))
      const submit = vi.fn(async () => {
        throw err
      })
      await flushQueue(submit, () => {})
      // Abbruch beim ersten Eintrag, nichts markiert, Reihenfolge bleibt
      expect(submit).toHaveBeenCalledTimes(1)
      expect(getQueuedPunches()).toEqual([queued('a'), queued('b')])
    }
  })

  it('versucht markierte Einträge nicht erneut, bis sie verworfen werden', async () => {
    enqueuePunch(queued('a', { error: 'PIN falsch.' }))
    enqueuePunch(queued('b'))
    const submit = vi.fn(async () => {})
    await flushQueue(submit, () => {})
    expect(submit).toHaveBeenCalledTimes(1)
    expect(keys()).toEqual(['a'])
    expect(discardQueuedPunch('a')).toEqual([])
  })

  it('meldet unbekannte Fehler verständlich', async () => {
    enqueuePunch(queued('a'))
    await flushQueue(async () => {
      throw new Error('kaputt')
    }, () => {})
    expect(getQueuedPunches()[0].error).toBe('Unbekannter Fehler.')
  })

  it('verliert keine Stempelung, die während des Sendens neu dazukommt', async () => {
    enqueuePunch(queued('a'))
    await flushQueue(async (punch) => {
      if (punch.idempotency_key === 'a') enqueuePunch(queued('neu'))
    }, () => {})
    // "neu" kam nach dem Start dazu: entweder gesendet oder noch in der Schlange – nie verloren.
    expect(keys()).not.toContain('a')
    expect(keys()).toEqual(['neu'])
  })

  it('verwerfen entfernt nur den gewählten Eintrag', () => {
    enqueuePunch(queued('a'))
    enqueuePunch(queued('b'))
    expect(keys(discardQueuedPunch('a'))).toEqual(['b'])
    expect(keys(discardQueuedPunch('gibt-es-nicht'))).toEqual(['b'])
  })
})
