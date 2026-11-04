/** Bildschirmzeiten am Kiosk: Mandanten-Einstellung und Abweichung je Tablet. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DeviceFormDialog } from '../devices/DeviceFormDialog'
import { settings } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { KioskDisplayCard } from './DefaultsSettingsCard'

function lastBody(calls: ApiCall[], method: string) {
  return calls.filter((call) => call.method === method).at(-1)?.init.body as Record<string, unknown> | undefined
}

async function setTime(label: string, value: string) {
  const input = screen.getByLabelText(label)
  await userEvent.clear(input)
  await userEvent.type(input, value)
}

describe('Einstellungen → Kiosk: Bildschirmzeiten', () => {
  it('ist standardmäßig aus (Bildschirm immer an) und speichert ein Zeitfenster', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'PATCH /settings': (init: ApiInit) => ({ ...settings(), ...(init.body as object) }) })
    renderWithProviders(<KioskDisplayCard settings={settings()} />)
    const toggle = screen.getByRole('checkbox', { name: /Bildschirm nur zu bestimmten Zeiten/ })
    expect(toggle).not.toBeChecked()
    expect(screen.queryByLabelText('Bildschirm an von')).not.toBeInTheDocument()

    await userEvent.click(toggle)
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false) // erst mit "Übernehmen"
    expect(screen.getByLabelText('Bildschirm an von')).toHaveValue('06:00')
    await setTime('Bildschirm an bis', '20:30')
    await userEvent.click(screen.getByRole('button', { name: 'Bildschirmzeiten übernehmen' }))
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ kiosk_screen_on_from: '06:00', kiosk_screen_on_until: '20:30' }))
  })

  it('verhindert gleiche Zeiten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({})
    renderWithProviders(<KioskDisplayCard settings={settings()} />)
    await userEvent.click(screen.getByRole('checkbox', { name: /Bildschirm nur zu bestimmten Zeiten/ }))
    await setTime('Bildschirm an bis', '06:00')
    expect(screen.getByRole('button', { name: 'Bildschirmzeiten übernehmen' })).toBeDisabled()
  })

  it('zeigt gespeicherte Zeiten und leert sie beim Ausschalten', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const current = settings({ kiosk_screen_on_from: '22:00:00', kiosk_screen_on_until: '06:00:00' })
    const calls = mockApi({ 'PATCH /settings': (init: ApiInit) => ({ ...current, ...(init.body as object) }) })
    renderWithProviders(<KioskDisplayCard settings={current} />)
    const toggle = screen.getByRole('checkbox', { name: /Bildschirm nur zu bestimmten Zeiten/ })
    expect(toggle).toBeChecked()
    expect(screen.getByLabelText('Bildschirm an von')).toHaveValue('22:00')
    expect(screen.getByLabelText('Bildschirm an bis')).toHaveValue('06:00')
    await userEvent.click(toggle)
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ clear_kiosk_screen_hours: true }))
  })
})

describe('Tablet bearbeiten: Bildschirmzeiten', () => {
  const LOCATIONS = [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }] as never

  function device(overrides: Record<string, unknown> = {}) {
    return {
      id: 4, location_id: 1, name: 'Eingang', device_token: 'x', last_seen: null, theme: null,
      screen_hours_mode: null, screen_on_from: null, screen_on_until: null, ...overrides,
    } as never
  }

  function renderDialog(current = device()) {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'PATCH /devices/{device_id}': (init: ApiInit) => ({ ...(current as object), ...(init.body as object) }) })
    const onOpenChange = vi.fn()
    renderWithProviders(<DeviceFormDialog open onOpenChange={onOpenChange} device={current} locations={LOCATIONS} />)
    return { calls, onOpenChange }
  }

  it('sendet "Wie Einstellungen" als Standard', async () => {
    const { calls, onOpenChange } = renderDialog()
    expect(screen.getByLabelText('Bildschirmzeiten')).toHaveValue('DEFAULT')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    const body = lastBody(calls, 'PATCH')
    expect(body).toMatchObject({ screen_hours_mode: 'DEFAULT' })
    expect(body).not.toHaveProperty('screen_on_from')
  })

  it('sendet "Immer an"', async () => {
    const { calls } = renderDialog()
    await userEvent.selectOptions(screen.getByLabelText('Bildschirmzeiten'), 'ALWAYS')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ screen_hours_mode: 'ALWAYS' }))
  })

  it('sendet eigene Zeiten über Mitternacht', async () => {
    const { calls } = renderDialog()
    await userEvent.selectOptions(screen.getByLabelText('Bildschirmzeiten'), 'CUSTOM')
    await setTime('Bildschirm an von', '22:00')
    await setTime('Bildschirm an bis', '06:00')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(lastBody(calls, 'PATCH')).toMatchObject({ screen_hours_mode: 'CUSTOM', screen_on_from: '22:00', screen_on_until: '06:00' }),
    )
  })

  it('zeigt gespeicherte eigene Zeiten und lehnt gleiche Zeiten ab', async () => {
    const { calls } = renderDialog(device({ screen_hours_mode: 'CUSTOM', screen_on_from: '05:30:00', screen_on_until: '20:00:00' }))
    expect(screen.getByLabelText('Bildschirmzeiten')).toHaveValue('CUSTOM')
    expect(screen.getByLabelText('Bildschirm an von')).toHaveValue('05:30')
    await setTime('Bildschirm an bis', '05:30')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/„von“ und „bis“ angeben \(nicht gleich\)/)).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false)
  })
})
