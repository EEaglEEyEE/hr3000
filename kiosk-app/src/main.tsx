import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './theme-inverted.css'
import App from './App.tsx'
import { registerSW } from 'virtual:pwa-register'

// Neue Kiosk-Versionen sofort übernehmen (lädt die Seite neu, sobald sie bereitsteht) und
// regelmäßig danach fragen – ein Kiosk-Tablet wird sonst tagelang nicht neu geladen.
registerSW({
  immediate: true,
  onRegisteredSW(_url, registration) {
    if (registration) setInterval(() => void registration.update(), 30 * 60 * 1000)
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
