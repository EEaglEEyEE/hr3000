/** Flexible Arbeitszeitmodelle unter „Zu klären“: Schalter in den Einstellungen und der Hinweis
 * „Wochensoll nicht erreicht“ in der Liste. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { OpenDayChecksCard } from '../components/settings/DefaultsSettingsCard'
import { DAY_FLAG_LABELS, WEEKLY_TARGET_MISSED } from '../lib/labels'
import { openDay, settings } from '../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../test/utils'
import { OpenDaysPage } from './OpenDaysPage'

function lastBody(calls: ApiCall[], method: string) {
  return [...calls].reverse().find((call) => call.method === method)?.init.body
}

function settingsRoutes(initial = settings({ disabled_day_flags: ['EARLY_LEAVE', 'LATE_ARRIVAL', WEEKLY_TARGET_MISSED] })) {
  const state = { current: initial }
  const calls = mockApi({
    'GET /settings': () => state.current,
    'PATCH /settings': (init: ApiInit) => {
      state.current = { ...state.current, ...(init.body as object) }
      return state.current
    },
  })
  return { state, calls }
}

describe('Einstellungen: Modell „Flexibel ohne feste Tage“ unter „Zu klären“', () => {
  it('zeigt den Standard: Tage werden gemeldet, das Wochensoll nicht', () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const { state } = settingsRoutes()
    renderWithProviders(<OpenDayChecksCard settings={state.current} />)
    expect(screen.getByRole('checkbox', { name: /Tage dieser Mitarbeiter melden/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Wochensoll nicht erreicht wurde/ })).not.toBeChecked()
    expect(screen.queryByText(/gelten nirgends als offen/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Der Hinweis steht am Sonntag/)).not.toBeInTheDocument()
    // Der Hinweis steht nicht noch einmal in der Liste der Sonderfälle
    expect(screen.queryByRole('checkbox', { name: DAY_FLAG_LABELS[WEEKLY_TARGET_MISSED] })).not.toBeInTheDocument()
  })

  it('schaltet die Tage flexibler Modelle ab und erklärt die Folgen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const { state, calls } = settingsRoutes()
    const { unmount } = renderWithProviders(<OpenDayChecksCard settings={state.current} />)
    await userEvent.click(screen.getByRole('checkbox', { name: /Tage dieser Mitarbeiter melden/ }))
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ report_flexible_days: false }))
    expect(lastBody(calls, 'PATCH')).not.toHaveProperty('disabled_day_flags')
    unmount()
    renderWithProviders(<OpenDayChecksCard settings={state.current} />)
    expect(screen.getByRole('checkbox', { name: /Tage dieser Mitarbeiter melden/ })).not.toBeChecked()
    expect(screen.getByText(/gelten nirgends als offen/)).toBeInTheDocument()
    expect(screen.getByText(/zählt mit 0 Stunden, es wird nichts geschätzt/)).toBeInTheDocument()
  })

  it('schaltet „Wochensoll nicht erreicht“ ein, ohne andere Häkchen zu ändern, und nennt den Stichtag', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const { state, calls } = settingsRoutes()
    const { unmount } = renderWithProviders(<OpenDayChecksCard settings={state.current} />)
    await userEvent.click(screen.getByRole('checkbox', { name: /Wochensoll nicht erreicht wurde/ }))
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toHaveProperty('disabled_day_flags', ['EARLY_LEAVE', 'LATE_ARRIVAL']))
    expect(lastBody(calls, 'PATCH')).not.toHaveProperty('report_flexible_days')
    unmount()
    renderWithProviders(<OpenDayChecksCard settings={{ ...state.current, weekly_target_from: '2026-11-13' }} />)
    expect(screen.getByRole('checkbox', { name: /Wochensoll nicht erreicht wurde/ })).toBeChecked()
    expect(screen.getByText(/Gemeldet werden Wochen ab dem 13\.11\.2026\./)).toBeInTheDocument()
  })

  it('schaltet „Wochensoll nicht erreicht“ wieder aus', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const { state, calls } = settingsRoutes(settings({ disabled_day_flags: ['EARLY_LEAVE'], weekly_target_from: null }))
    renderWithProviders(<OpenDayChecksCard settings={state.current} />)
    // Ohne Stichtag: Erklärung ohne Datum
    expect(screen.getByText(/Der Hinweis steht am Sonntag/)).toBeInTheDocument()
    expect(screen.queryByText(/Gemeldet werden Wochen ab dem/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox', { name: /Wochensoll nicht erreicht wurde/ }))
    await waitFor(() =>
      expect((lastBody(calls, 'PATCH') as { disabled_day_flags: string[] }).disabled_day_flags.sort()).toEqual(['EARLY_LEAVE', WEEKLY_TARGET_MISSED]),
    )
  })
})

describe('Zu klären: Wochensoll nicht erreicht', () => {
  const sunday = {
    ...openDay(4, '2026-11-08'),
    first_name: 'Fiona',
    last_name: 'Flexibel',
    times: '',
    flags: [WEEKLY_TARGET_MISSED],
    week_target_minutes: 480,
    week_actual_minutes: 300,
  }

  function routes(days: unknown[]) {
    let current = [...days]
    return {
      'GET /locations': [],
      'GET /punch-correction-requests': [],
      'GET /timesheet/monthly-caps': [],
      'GET /timesheet/open-days': () => current,
      'PUT /employees/{employee_id}/day-reviews/{work_date}': () => {
        current = []
        return undefined
      },
    }
  }

  function row(date: string) {
    return screen.getByText(date).closest('tr') as HTMLElement
  }

  it('zeigt Grund und Wochenstunden statt „Stempelung fehlt“', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(routes([sunday]))
    renderWithProviders(<OpenDaysPage />)
    await screen.findByText('8.11.2026')
    const cells = within(row('8.11.2026'))
    expect(cells.getByText(DAY_FLAG_LABELS[WEEKLY_TARGET_MISSED])).toBeInTheDocument()
    expect(cells.getByText('Woche: 5:00 von 8:00 Std.')).toBeInTheDocument()
    expect(cells.queryByText('Stempelung fehlt')).not.toBeInTheDocument()
  })

  it('markiert die Woche ohne Rückfrage als erledigt', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const confirm = vi.spyOn(window, 'confirm')
    const calls = mockApi(routes([sunday]))
    renderWithProviders(<OpenDaysPage />)
    await screen.findByText('8.11.2026')
    await userEvent.click(within(row('8.11.2026')).getByRole('button', { name: 'Erledigt' }))
    await waitFor(() => expect(screen.queryByText('8.11.2026')).not.toBeInTheDocument())
    expect(confirm).not.toHaveBeenCalled()
    expect(calls.find((call) => call.method === 'PUT')?.init.params?.path).toEqual({ employee_id: 4, work_date: '2026-11-08' })
  })

  it('fragt weiter nach, wenn am Abrechnungstag selbst unvollständig gestempelt wurde', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const calls = mockApi(routes([{ ...sunday, times: '08:00–…' }]))
    renderWithProviders(<OpenDaysPage />)
    await screen.findByText('8.11.2026')
    // Mit eigener Stempelung bleibt der Status des Tages sichtbar
    expect(within(row('8.11.2026')).getByText('Woche: 5:00 von 8:00 Std.')).toBeInTheDocument()
    await userEvent.click(within(row('8.11.2026')).getByRole('button', { name: 'Erledigt' }))
    expect(confirm).toHaveBeenCalled()
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)
  })

  it('zeigt bei anderen Tagen keine Wochenzeile', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi(routes([openDay(2, '2026-10-19')]))
    renderWithProviders(<OpenDaysPage />)
    await screen.findByText('19.10.2026')
    expect(screen.queryByText(/^Woche:/)).not.toBeInTheDocument()
    expect(within(row('19.10.2026')).getAllByText('Stempelung fehlt').length).toBeGreaterThan(0)
  })
})
