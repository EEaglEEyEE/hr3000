/** QR-Code fürs Tablet: ohne Chip wird eine zufällige Chip-UID vergeben und als QR-Code gezeigt. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { EmployeeFormDialog } from './EmployeeFormDialog'

const LOCATIONS = [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }] as never

describe('QR-Code fürs Tablet', () => {
  it('vergibt eine Chip-UID und zeigt den QR-Code', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /features': { shift_planning_enabled: false, absence_requests_enabled: true, default_auto_break: true, default_show_birthday: true, default_day_minutes: null },
    })
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await userEvent.type(await screen.findByLabelText('Vorname'), 'Paula')
    await userEvent.type(screen.getByLabelText('Nachname'), 'Probe')
    await userEvent.click(screen.getByText(/Login und Stempeln am Tablet/))
    await userEvent.click(screen.getByRole('button', { name: 'QR-Code fürs Tablet' }))
    expect((screen.getByLabelText('Chip-UID (optional)') as HTMLInputElement).value).toMatch(/^[0-9A-F]{16}$/)
    await waitFor(() => expect(screen.getByLabelText('QR-Code für Paula Probe').innerHTML).toContain('<svg'))
    expect(screen.getByText(/Neue Chip-UID – bitte unten speichern/)).toBeInTheDocument()
  })
})
