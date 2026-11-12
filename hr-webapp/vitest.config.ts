import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Eigene Test-Konfiguration ohne Tailwind/PWA-Plugins – Komponententests brauchen kein CSS.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    restoreMocks: true,
    // Im Docker-Build auf dem Server (CPU geteilt mit Prod, Backend-Tests laufen gleichzeitig) brauchen
    // Formular-Tests mit vielen Tastendrücken teils über 5 s – das Standardlimit ließ den Staging-Build
    // am 07.11.2026 scheitern. Am 12.11.2026 brauchte der erste Test von „Mein Bereich“ (erstes Laden
    // der großen Seite) dort 25 s und riss das 15-s-Limit; lokal läuft er in unter 2 s.
    testTimeout: 60_000,
  },
})
