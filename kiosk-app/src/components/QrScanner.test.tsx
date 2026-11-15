/** QR-Scanner: Kamera wird immer freigegeben, Abbruch beim Schließen ist kein Kamerafehler. */
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isQrScanSupported, QrScanner } from './QrScanner'

let detected: { rawValue: string }[] = []
const stopTrack = vi.fn()
const fakeStream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

class FakeDetector {
  detect = vi.fn(async () => detected)
}

beforeEach(() => {
  vi.useFakeTimers()
  detected = []
  stopTrack.mockClear()
  Object.defineProperty(window, 'BarcodeDetector', { value: FakeDetector, configurable: true, writable: true })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  Reflect.deleteProperty(window, 'BarcodeDetector')
  Reflect.deleteProperty(navigator, 'mediaDevices')
})

function mockCamera(getUserMedia: () => Promise<MediaStream>) {
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: vi.fn(getUserMedia) }, configurable: true })
}

const ERROR = 'Kamera nicht verfügbar oder Zugriff nicht erlaubt.'

describe('QR-Scanner', () => {
  it('ist nur mit BarcodeDetector und Kamera-Zugriff verfügbar', () => {
    expect(isQrScanSupported()).toBe(false) // keine mediaDevices
    mockCamera(async () => fakeStream)
    expect(isQrScanSupported()).toBe(true)
    Reflect.deleteProperty(window, 'BarcodeDetector')
    expect(isQrScanSupported()).toBe(false)
  })

  it('liest einen QR-Code einmal und gibt die Kamera beim Schließen frei', async () => {
    mockCamera(async () => fakeStream)
    const onResult = vi.fn()
    const view = render(<QrScanner onResult={onResult} onCancel={() => {}} />)
    await act(async () => {})
    detected = [{ rawValue: 'https://kiosk.example.com/#pair=ABCD-EFGH' }]
    await act(async () => {
      await vi.advanceTimersByTimeAsync(700)
    })
    expect(onResult).toHaveBeenCalledTimes(1)
    expect(onResult).toHaveBeenCalledWith('https://kiosk.example.com/#pair=ABCD-EFGH')
    view.unmount()
    expect(stopTrack).toHaveBeenCalled()
  })

  it('zeigt einen Fehler, wenn die Kamera verweigert wird', async () => {
    mockCamera(async () => {
      throw new DOMException('verweigert', 'NotAllowedError')
    })
    render(<QrScanner onResult={() => {}} onCancel={() => {}} />)
    await act(async () => {})
    expect(screen.getByText(ERROR)).toBeInTheDocument()
  })

  it('gibt eine Kamera frei, die erst nach dem Schließen startet (kein Fehler)', async () => {
    const camera = deferred<MediaStream>()
    mockCamera(() => camera.promise)
    const view = render(<QrScanner onResult={() => {}} onCancel={() => {}} />)
    view.unmount()
    await act(async () => {
      camera.resolve(fakeStream)
    })
    expect(stopTrack).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(ERROR)).toBeNull()
  })

  it('wertet ein beim Schließen abgebrochenes play() nicht als Kamerafehler', async () => {
    const playback = deferred<void>()
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockReturnValue(playback.promise)
    mockCamera(async () => fakeStream)
    const errors: string[] = []
    const view = render(<QrScanner onResult={() => {}} onCancel={() => {}} />)
    await act(async () => {})
    const container = view.container
    view.unmount()
    await act(async () => {
      playback.reject(new DOMException('unterbrochen', 'AbortError'))
    })
    if (container.textContent?.includes(ERROR)) errors.push('Fehler angezeigt')
    expect(errors).toEqual([])
    expect(stopTrack).toHaveBeenCalled()
  })

  it('React StrictMode: doppelter Start gibt die erste Kamera frei, spielt nur einmal ab, kein Fehler', async () => {
    const { StrictMode } = await import('react')
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
    mockCamera(async () => fakeStream)
    const view = render(
      <StrictMode>
        <QrScanner onResult={() => {}} onCancel={() => {}} />
      </StrictMode>,
    )
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2)
    expect(play).toHaveBeenCalledTimes(1)
    expect(stopTrack).toHaveBeenCalledTimes(1) // nur die Kamera des verworfenen ersten Starts
    expect(screen.queryByText(ERROR)).toBeNull()
    view.unmount()
    expect(stopTrack).toHaveBeenCalledTimes(2)
  })
})
