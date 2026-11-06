/** Anmeldung am Tablet: eine Auswahl statt fünf Schalter – bildet die bisherigen Felder eindeutig ab. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { settings } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { KioskLoginCard, kioskLoginMode } from './DefaultsSettingsCard'

function lastPatch(calls: ApiCall[]) {
  return calls.filter((call) => call.method === 'PATCH').at(-1)?.init.body as Record<string, unknown> | undefined
}

describe('Anmeldung am Tablet', () => {
  it('ordnet jede bisherige Kombination genau einer Auswahl zu', () => {
    const combos = [
      { require_pin_for_punch: false, kiosk_rfid_enabled: false, rfid_required: false, mode: 'TAP' },
      { require_pin_for_punch: true, kiosk_rfid_enabled: false, rfid_required: false, mode: 'TAP_PIN' },
      { require_pin_for_punch: false, kiosk_rfid_enabled: true, rfid_required: false, mode: 'TAP_OR_CHIP' },
      { require_pin_for_punch: true, kiosk_rfid_enabled: true, rfid_required: false, mode: 'PIN_OR_CHIP' },
      { require_pin_for_punch: false, kiosk_rfid_enabled: true, rfid_required: true, mode: 'CHIP_ONLY' },
      { require_pin_for_punch: true, kiosk_rfid_enabled: true, rfid_required: true, mode: 'CHIP_ONLY' },
      // RFID-Pflicht ohne Chip-Funktion wirkt am Tablet nicht
      { require_pin_for_punch: true, kiosk_rfid_enabled: false, rfid_required: true, mode: 'TAP_PIN' },
    ]
    for (const { mode, ...fields } of combos) expect(kioskLoginMode(fields)).toBe(mode)
  })

  it('speichert die gewählte Anmeldung mit allen zugehörigen Feldern', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const current = settings({ require_pin_for_punch: false, kiosk_rfid_enabled: true, rfid_required: false })
    const calls = mockApi({ 'PATCH /settings': (init: ApiInit) => ({ ...current, ...(init.body as object) }) })
    renderWithProviders(<KioskLoginCard settings={current} />)
    expect(screen.getByRole('radio', { name: /Kachel antippen oder Chip vorhalten/ })).toBeChecked()
    // Chip im Spiel: Selbst-Registrierung und (dafür) PIN-Festlegung sichtbar
    expect(screen.getByRole('checkbox', { name: /registrieren ihren Chip selbst/ })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /PIN beim ersten Mal selbst festlegen/ })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /Kachel antippen \+ PIN/ }))
    await waitFor(() =>
      expect(lastPatch(calls)).toMatchObject({ require_pin_for_punch: true, kiosk_rfid_enabled: false, rfid_required: false }),
    )
    await userEvent.click(screen.getByRole('radio', { name: /Nur Chip/ }))
    await waitFor(() => expect(lastPatch(calls)).toMatchObject({ kiosk_rfid_enabled: true, rfid_required: true }))
  })

  it('zeigt ohne PIN und Chip keine Selbst-Einrichtung', () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({})
    renderWithProviders(<KioskLoginCard settings={settings({ require_pin_for_punch: false, kiosk_rfid_enabled: false })} />)
    expect(screen.getByRole('radio', { name: /^Kachel antippen\s*Ohne PIN/ })).toBeChecked()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })
})
