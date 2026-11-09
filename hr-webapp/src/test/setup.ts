import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(async () => {
  cleanup()
  localStorage.clear()
  vi.useRealTimers()
  // Radix (FocusScope) feuert beim Schließen eines Dialogs ein Ereignis per setTimeout(0). Ohne diesen
  // Takt lief es unter Last (Docker-Build) manchmal erst nach dem Abbau von jsdom: „dispatchEvent …
  // parameter 1 is not of type 'Event'“ als unbehandelter Fehler, Testlauf rot.
  await new Promise((resolve) => setTimeout(resolve, 0))
})

// jsdom kennt einige Browser-APIs nicht, die Radix-UI (Select, Tabs, Dialog) voraussetzt.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView ??= () => {}
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}
window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia
