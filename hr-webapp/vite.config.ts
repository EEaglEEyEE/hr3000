import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        // changeOrigin:false, damit der Original-Host-Header des Browsers
        // (z.B. musterfirma.localhost, admin.hrapp3000.localhost) beim
        // Backend ankommt – die Tenant-Resolution-Middleware braucht ihn zur
        // Mandanten-Auflösung, siehe backend/app/middleware/tenant.py.
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
