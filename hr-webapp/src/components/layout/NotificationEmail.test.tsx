/** Glocke: persönliche Einstellung „Benachrichtigungen auch per E-Mail“. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../../test/utils'
import { NotificationBell } from './NotificationBell'

afterEach(() => vi.restoreAllMocks())

describe('Benachrichtigungen per E-Mail', () => {
  it('schaltet E-Mails für die eigene Person ab', async () => {
    loginAs({ kind: 'employee', employeeId: 5 })
    const calls = mockApi({
      'GET /notifications': [],
      'GET /notifications/settings': { email: true },
      'PUT /notifications/settings': (init: ApiInit) => init.body,
    })
    renderWithProviders(<NotificationBell />)
    await userEvent.click(screen.getByRole('button', { name: /Benachrichtigungen/ }))
    const toggle = await screen.findByLabelText(/Benachrichtigungen auch per E-Mail/)
    expect(toggle).toBeChecked()
    await userEvent.click(toggle)
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.init.body).toEqual({ email: false }))
  })
})
