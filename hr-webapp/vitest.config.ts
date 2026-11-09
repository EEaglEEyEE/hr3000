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
    // Im Docker-Build auf dem Server (CPU geteilt mit Prod) brauchen Formular-Tests mit vielen
    // Tastendrücken teils über 5 s – das Standardlimit ließ den Staging-Build am 07.11.2026 scheitern.
    testTimeout: 15_000,
  },
})
