/** Android-App „HR3000 Kiosk“: feste Installations-Kennung und Bildschirmsteuerung über window.HR3000Native. */
import { act, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installationId } from './installation'
import { nativeBridge, nativeInstallationId, nativeKeepAwake, type HR3000Native } from './nativeBridge'
import { useWakeLock } from './wakeLock'

const NATIVE_ID = 'and1-Qk3x9vB2mN8pL4tR7wY1zA5cE6fH0jK2sD9gU3iO7qV'

function installBridge(overrides: Partial<HR3000Native> = {}): HR3000Native {
  const bridge: HR3000Native = {
    installationId: vi.fn(() => NATIVE_ID),
    setKeepAwake: vi.fn(),
    appVersion: vi.fn(() => '1.0.0'),
    platform: vi.fn(() => 'android'),
    ...overrides,
  }
  window.HR3000Native = bridge
  return bridge
}

afterEach(() => {
  delete window.HR3000Native
  localStorage.clear()
  vi.restoreAllMocks()
  Reflect.deleteProperty(navigator, 'wakeLock')
})

describe('Schnittstelle zur Android-App', () => {
  it('fehlt im Browser', () => {
    expect(nativeBridge()).toBeNull()
    expect(nativeInstallationId()).toBeNull()
    expect(nativeKeepAwake(true)).toBe(false)
  })

  it('ignoriert ein fremdes Objekt ohne die erwarteten Methoden', () => {
    window.HR3000Native = {} as HR3000Native
    expect(nativeBridge()).toBeNull()
    expect(nativeInstallationId()).toBeNull()
  })

  it('liefert die Kennung der App', () => {
    installBridge()
    expect(nativeInstallationId()).toBe(NATIVE_ID)
  })

  it('verwirft leere, zu kurze, zu lange oder seltsame Kennungen', () => {
    for (const bad of ['', '   ', 'kurz', 'x'.repeat(101), 'and1-mit leerzeichen-0123456789', 'and1-<script>0123456789']) {
      installBridge({ installationId: () => bad })
      expect(nativeInstallationId(), bad).toBeNull()
    }
    installBridge({ installationId: () => 'x'.repeat(16) })
    expect(nativeInstallationId()).toBe('x'.repeat(16))
    installBridge({ installationId: () => ` ${'y'.repeat(100)} ` })
    expect(nativeInstallationId()).toBe('y'.repeat(100))
  })

  it('übersteht eine werfende App-Schnittstelle', () => {
    installBridge({
      installationId: () => {
        throw new Error('weg')
      },
      setKeepAwake: () => {
        throw new Error('weg')
      },
    })
    expect(nativeInstallationId()).toBeNull()
    expect(nativeKeepAwake(true)).toBe(false)
  })

  it('schaltet den Bildschirm über die App', () => {
    const bridge = installBridge()
    expect(nativeKeepAwake(true)).toBe(true)
    expect(nativeKeepAwake(false)).toBe(true)
    expect(bridge.setKeepAwake).toHaveBeenNthCalledWith(1, true)
    expect(bridge.setKeepAwake).toHaveBeenNthCalledWith(2, false)
  })
})

describe('Installations-ID in der App', () => {
  it('übernimmt beim ersten Start die Kennung der App und speichert sie', () => {
    installBridge()
    expect(installationId()).toBe(NATIVE_ID)
    expect(localStorage.getItem('kiosk.installation_id')).toBe(NATIVE_ID)
  })

  it('nach „Daten löschen“ kommt dieselbe Kennung wieder', () => {
    installBridge()
    const first = installationId()
    localStorage.clear()
    expect(installationId()).toBe(first)
  })

  it('behält eine schon gespeicherte ID (sonst wäre die Bindung weg)', () => {
    localStorage.setItem('kiosk.installation_id', 'alte-zufalls-id-0123456789')
    const bridge = installBridge()
    expect(installationId()).toBe('alte-zufalls-id-0123456789')
    expect(bridge.installationId).not.toHaveBeenCalled()
  })

  it('fällt ohne brauchbare Kennung auf eine Zufalls-ID zurück', () => {
    installBridge({ installationId: () => '' })
    const id = installationId()
    expect(id).not.toBe('')
    expect(id.startsWith('and1-')).toBe(false)
    expect(id.length).toBeGreaterThanOrEqual(30)
  })
})

function WakeLockProbe({ active }: { active: boolean }) {
  useWakeLock(active)
  return null
}

describe('Bildschirm anlassen in der App', () => {
  it('nutzt die App statt der Screen Wake Lock API und gibt beim Verlassen frei', () => {
    const bridge = installBridge()
    const request = vi.fn()
    Object.defineProperty(navigator, 'wakeLock', { value: { request }, configurable: true })
    const view = render(<WakeLockProbe active />)
    expect(bridge.setKeepAwake).toHaveBeenLastCalledWith(true)
    expect(request).not.toHaveBeenCalled()
    view.rerender(<WakeLockProbe active={false} />)
    expect(bridge.setKeepAwake).toHaveBeenLastCalledWith(false)
    view.rerender(<WakeLockProbe active />)
    expect(bridge.setKeepAwake).toHaveBeenLastCalledWith(true)
    view.unmount()
    expect(bridge.setKeepAwake).toHaveBeenLastCalledWith(false)
  })

  it('nutzt im Browser weiter die Screen Wake Lock API', async () => {
    const release = vi.fn(() => Promise.resolve())
    const request = vi.fn(() => Promise.resolve({ release }))
    Object.defineProperty(navigator, 'wakeLock', { value: { request }, configurable: true })
    const view = render(<WakeLockProbe active />)
    await act(async () => {})
    expect(request).toHaveBeenCalledWith('screen')
    view.unmount()
    expect(release).toHaveBeenCalled()
  })
})
