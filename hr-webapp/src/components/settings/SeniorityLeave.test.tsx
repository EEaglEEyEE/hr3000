/** Zusatzurlaub nach Betriebszugehörigkeit: Stufen anlegen und sortiert speichern. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { settings as defaultSettings } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { SeniorityLeaveCard } from './DefaultsSettingsCard'

afterEach(() => vi.restoreAllMocks())

describe('Zusatzurlaub nach Betriebszugehörigkeit', () => {
  it('speichert die Stufen aufsteigend', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'PATCH /settings': (init: ApiInit) => ({ ...defaultSettings(), ...(init.body as object) }) })
    renderWithProviders(<SeniorityLeaveCard settings={{ ...defaultSettings(), seniority_leave_rules: [{ years: 10, days: 2 }] }} />)
    await userEvent.click(screen.getByRole('button', { name: 'Stufe hinzufügen' }))
    await userEvent.type(screen.getByLabelText('Jahre Stufe 2'), '5')
    await userEvent.click(screen.getByRole('button', { name: 'Übernehmen' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.init.body).toMatchObject({
        seniority_leave_rules: [{ years: 5, days: 1 }, { years: 10, days: 2 }],
      }),
    )
  })
})
