/** Bildschirmzeiten: Zeitfenster in der Standort-Zeitzone und Wake Lock nur innerhalb des Fensters. */
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isWithinScreenHours, useScreenHours } from './screenHours'
import { useWakeLock } from './wakeLock'

const BERLIN = 'Europe/Berlin'
const at = (iso: string) => new Date(iso)

describe('isWithinScreenHours', () => {
  it('ohne Fenster ist der Bildschirm immer an', () => {
    expect(isWithinScreenHours(at('2026-11-04T02:00:00Z'), null, null, BERLIN)).toBe(true)
    expect(isWithinScreenHours(at('2026-11-04T02:00:00Z'), '06:00', null, BERLIN)).toBe(true)
  })

  it.each([
    ['2026-11-04T04:59:00Z', false], // 05:59 MEZ
    ['2026-11-04T05:00:00Z', true], // 06:00 MEZ – Beginn gehört dazu
    ['2026-11-04T12:00:00Z', true],
    ['2026-11-04T19:59:00Z', true], // 20:59
    ['2026-11-04T20:00:00Z', false], // 21:00 – Ende gehört nicht dazu
  ])('06:00–21:00 Berlin um %s -> %s', (iso, expected) => {
    expect(isWithinScreenHours(at(iso), '06:00', '21:00', BERLIN)).toBe(expected)
  })

  it.each([
    ['2026-11-04T21:30:00Z', true], // 22:30
    ['2026-11-04T23:30:00Z', true], // 00:30
    ['2026-11-05T04:59:00Z', true], // 05:59
    ['2026-11-05T05:00:00Z', false], // 06:00
    ['2026-11-04T11:00:00Z', false], // 12:00
  ])('über Mitternacht 22:00–06:00 um %s -> %s', (iso, expected) => {
    expect(isWithinScreenHours(at(iso), '22:00', '06:00', BERLIN)).toBe(expected)
  })

  it('rechnet über die Umstellung auf Sommerzeit (29.03.2026) mit der Standortzeit', () => {
    expect(isWithinScreenHours(at('2026-03-28T04:30:00Z'), '06:00', '21:00', BERLIN)).toBe(false) // 05:30 MEZ
    expect(isWithinScreenHours(at('2026-03-29T04:30:00Z'), '06:00', '21:00', BERLIN)).toBe(true) // 06:30 MESZ
    expect(isWithinScreenHours(at('2026-03-29T19:00:00Z'), '06:00', '21:00', BERLIN)).toBe(false) // 21:00 MESZ
  })

  it('rechnet über die Umstellung auf Winterzeit (25.10.2026) mit der Standortzeit', () => {
    expect(isWithinScreenHours(at('2026-10-24T03:30:00Z'), '06:00', '21:00', BERLIN)).toBe(false) // 05:30 MESZ
    expect(isWithinScreenHours(at('2026-10-25T05:30:00Z'), '06:00', '21:00', BERLIN)).toBe(true) // 06:30 MEZ
    expect(isWithinScreenHours(at('2026-10-25T04:30:00Z'), '06:00', '21:00', BERLIN)).toBe(false) // 05:30 MEZ
  })

  it('nutzt die Standortzeit, nicht die Geräteuhr', () => {
    // 05:30 UTC = 06:30 in Berlin, aber 01:30 in New York
    expect(isWithinScreenHours(at('2026-11-04T05:30:00Z'), '06:00', '21:00', BERLIN)).toBe(true)
    expect(isWithinScreenHours(at('2026-11-04T05:30:00Z'), '06:00', '21:00', 'America/New_York')).toBe(false)
  })

  it('fällt bei ungültiger Zeitzone auf die Geräteuhr zurück, statt abzustürzen', () => {
    const local = new Date(2026, 10, 4, 5, 0) // 05:00 Geräteuhr
    expect(isWithinScreenHours(local, '06:00', '21:00', 'Mond/Basis')).toBe(false)
    expect(isWithinScreenHours(new Date(2026, 10, 4, 7, 0), '06:00', '21:00', 'Mond/Basis')).toBe(true)
  })

  it('lässt den Bildschirm bei unlesbaren oder gleichen Zeiten an', () => {
    expect(isWithinScreenHours(at('2026-11-04T02:00:00Z'), 'morgens', '21:00', BERLIN)).toBe(true)
    expect(isWithinScreenHours(at('2026-11-04T02:00:00Z'), '06:00', '06:00', BERLIN)).toBe(true)
  })
})

describe('Wake Lock nur im Zeitfenster', () => {
  let request: ReturnType<typeof vi.fn>
  let release: ReturnType<typeof vi.fn>

  function Probe({ from, until }: { from: string | null; until: string | null }) {
    const within = useScreenHours(from, until, BERLIN)
    useWakeLock(within)
    return <span data-within={within} />
  }

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval', 'setTimeout', 'clearTimeout'] })
    release = vi.fn(async () => {})
    request = vi.fn(async () => ({ release }))
    Object.defineProperty(navigator, 'wakeLock', { value: { request }, configurable: true })
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  })

  afterEach(() => {
    Reflect.deleteProperty(navigator, 'wakeLock')
  })

  async function flush() {
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('gibt die Sperre beim Verlassen des Fensters frei und fordert sie beim Wiedereintritt neu an', async () => {
    vi.setSystemTime(at('2026-11-04T19:58:00Z')) // 20:58 Berlin
    render(<Probe from="06:00" until="21:00" />)
    await flush()
    expect(request).toHaveBeenCalledTimes(1)
    expect(release).not.toHaveBeenCalled()

    await act(async () => {
      vi.setSystemTime(at('2026-11-04T20:00:30Z')) // 21:00:30 Berlin
      vi.advanceTimersByTime(60_000)
    })
    await flush()
    expect(release).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.setSystemTime(at('2026-11-05T05:00:10Z')) // 06:00:10 Berlin
      vi.advanceTimersByTime(60_000)
    })
    await flush()
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('hält die Sperre ohne Fenster dauerhaft', async () => {
    vi.setSystemTime(at('2026-11-04T02:00:00Z'))
    render(<Probe from={null} until={null} />)
    await flush()
    await act(async () => {
      vi.advanceTimersByTime(10 * 60_000)
    })
    expect(request).toHaveBeenCalledTimes(1)
    expect(release).not.toHaveBeenCalled()
  })

  it('reagiert sofort auf neue Zeiten aus der Kiosk-Konfiguration', async () => {
    vi.setSystemTime(at('2026-11-04T12:00:00Z')) // 13:00 Berlin
    const { rerender } = render(<Probe from={null} until={null} />)
    await flush()
    expect(request).toHaveBeenCalledTimes(1)
    rerender(<Probe from="22:00" until="06:00" />)
    await flush()
    expect(release).toHaveBeenCalledTimes(1)
  })
})
