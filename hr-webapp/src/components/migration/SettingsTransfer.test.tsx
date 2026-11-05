/** Einstellungen übertragen: Datei wählen -> Vorschau -> Übernehmen. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { SettingsTransferCard } from './SettingsTransferCard'

const exported = { format: 'hr3000-settings', version: 1, settings: { punctuality_check: true }, break_rules: [], absence_types: [], surcharge_rules: [] }

describe('Einstellungen übertragen', () => {
  it('zeigt die Vorschau und übernimmt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'POST /migration/settings-import': (init: ApiInit) => ({
        applied: init.params?.query?.apply === true,
        changes: ['Einstellung punctuality_check', 'Feste Pausenzeit 12:00–12:30'],
        skipped: ['Pausenregel ab 540 Min.: 45 Min.: kollidiert mit einer vorhandenen Regel'],
      }),
    })
    renderWithProviders(<SettingsTransferCard />)
    const file = new File([JSON.stringify(exported)], 'hr3000-einstellungen.json', { type: 'application/json' })
    await userEvent.upload(screen.getByLabelText('Einstellungs-Datei'), file)

    expect(await screen.findByText('Vorschau: 2 Änderung(en).')).toBeInTheDocument()
    expect(screen.getByText('Feste Pausenzeit 12:00–12:30')).toBeInTheDocument()
    expect(screen.getByText(/kollidiert/)).toBeInTheDocument()
    expect(calls[0].init.body).toEqual(exported)

    await userEvent.click(screen.getByRole('button', { name: 'Übernehmen' }))
    expect(await screen.findByText('Übernommen: 2 Änderung(en).')).toBeInTheDocument()
    await waitFor(() => expect(calls.at(-1)?.init.params?.query).toEqual({ apply: true }))
  })

  it('meldet eine kaputte Datei', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({})
    renderWithProviders(<SettingsTransferCard />)
    await userEvent.upload(screen.getByLabelText('Einstellungs-Datei'), new File(['kein json'], 'x.json', { type: 'application/json' }))
    expect(await screen.findByText('Die Datei ist keine gültige Einstellungs-Datei (JSON).')).toBeInTheDocument()
  })
})
