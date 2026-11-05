/** Festes Monatssoll im Arbeitszeitmodell und Schalter "Arbeitstage ganz ohne Stempelung". */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { settings } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { RulesCard } from '../settings/DefaultsSettingsCard'
import { WorkTimeModelTab } from './WorkTimeModelTab'

const monthlyModel = {
  employee_id: 7,
  configured: true,
  is_work_time_model: true,
  template_name: 'Arbeitszeitmodell 108.5 h/Monat',
  weekly_minutes: null,
  daily_minutes: null,
  weekdays: [0, 1, 2, 3, 4],
  day_minutes: null,
  monthly_minutes: 6510,
  valid_from: '2026-11-01',
}

function lastBody(calls: ApiCall[], method: string) {
  return calls.filter((call) => call.method === method).at(-1)?.init.body as Record<string, unknown> | undefined
}

describe('Arbeitszeitmodell: Monatsstunden', () => {
  it('speichert ein festes Monatssoll mit Arbeitstagen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /employees/{employee_id}/work-time-model': { ...monthlyModel, configured: false, monthly_minutes: null },
      'GET /employees/{employee_id}/work-time-model/history': [],
      'PUT /employees/{employee_id}/work-time-model': monthlyModel,
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)

    await userEvent.click(await screen.findByRole('button', { name: 'Monatsstunden (fest)' }))
    const save = screen.getByRole('button', { name: 'Speichern' })
    expect(save).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Monatsstunden'), '108,5')
    // Mo–Fr: 20 bis 23 Arbeitstage im Monat
    expect(screen.getByText(/je nach Monat 4,72–5,43 h pro Arbeitstag/)).toBeInTheDocument()
    await userEvent.click(save)
    await waitFor(() =>
      expect(lastBody(calls, 'PUT')).toMatchObject({ monthly_hours: 108.5, weekdays: [0, 1, 2, 3, 4], flexible: false }),
    )
  })

  it('zeigt das gültige Monatsmodell und den Verlauf', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({
      'GET /employees/{employee_id}/work-time-model': monthlyModel,
      'GET /employees/{employee_id}/work-time-model/history': [
        { ...monthlyModel, id: 3, valid_to: null, uneven: false, flexible: false, on_demand: false, monthly_cap_minutes: null },
      ],
    })
    renderWithProviders(<WorkTimeModelTab employeeId={7} canEdit />)
    expect(await screen.findByText('108,5 Std.')).toBeInTheDocument()
    expect(screen.getByText('pro Monat')).toBeInTheDocument()
    expect(screen.getByText('108,5 h/Monat an Mo, Di, Mi, Do, Fr')).toBeInTheDocument()
    // Formular mit dem gültigen Modell vorbelegt
    await waitFor(() => expect(screen.getByLabelText('Monatsstunden')).toHaveValue('108,5'))
  })
})

describe('Einstellungen: Arbeitstage ohne Stempelung', () => {
  it('schaltet die Meldung ab und erklärt die Folgen', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    let current = settings()
    const calls = mockApi({
      'GET /settings': () => current,
      'PATCH /settings': (init: ApiInit) => {
        current = { ...current, ...(init.body as object) }
        return current
      },
    })
    const { unmount } = renderWithProviders(<RulesCard settings={current} />)
    const box = screen.getByRole('checkbox', { name: /Arbeitstage ganz ohne Stempelung/ })
    expect(box).toBeChecked()
    expect(screen.queryByText(/Nur unvollständig gestempelte Tage/)).not.toBeInTheDocument()
    await userEvent.click(box)
    await waitFor(() => expect(lastBody(calls, 'PATCH')).toMatchObject({ report_days_without_punches: false }))
    unmount()
    renderWithProviders(<RulesCard settings={current} />)
    expect(screen.getByText(/Nur unvollständig gestempelte Tage/)).toBeInTheDocument()
  })
})
