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
  },
})
