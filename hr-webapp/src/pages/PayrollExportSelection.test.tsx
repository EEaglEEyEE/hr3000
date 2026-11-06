/** Lohn-Export: alle im Monat Beschäftigten (auch im Monat Ausgetretene), Vormonat vorbelegt. */
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { previousYearMonth } from '../lib/format'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { PayrollExportPage } from './PayrollExportPage'

function employee(id: number, extra: Record<string, unknown>) {
  return { id, first_name: `M${id}`, last_name: 'Test', employee_number: String(id), active: true, hire_date: null, termination_date: null, ...extra }
}

afterEach(() => vi.restoreAllMocks())

describe('Lohn-Export: Auswahl der Mitarbeiter', () => {
  it('nimmt im Monat Ausgetretene mit und lässt nicht Beschäftigte weg', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      'GET /locations': [],
      'GET /employees': [
        employee(1, {}),
        employee(2, { active: false, termination_date: '2026-08-15' }), // im August ausgetreten
        employee(3, { active: false, termination_date: '2026-07-31' }), // schon vorher weg
        employee(4, { hire_date: '2026-09-01' }), // erst später eingetreten
        employee(5, { active: false }), // inaktiv ohne Datum
      ],
    })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('x', { status: 200 }))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    renderWithProviders(<PayrollExportPage />)

    expect(screen.getByLabelText('Monat')).toHaveValue(previousYearMonth())
    fireEvent.change(screen.getByLabelText('Monat'), { target: { value: '2026-08' } })
    expect(await screen.findByText(/2 Mitarbeiter/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /CSV exportieren/ }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://x')
    expect(url.searchParams.getAll('employee_ids')).toEqual(['1', '2'])
    expect(url.searchParams.get('from')).toBe('2026-08-01')
  })
})

describe('Lohn-Export: Stand des Monats', () => {
  it('zeigt den Monatsabschluss und frühere Exporte', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /locations': [],
      'GET /employees': [employee(1, {}), employee(2, {})],
      'GET /payroll-export/status': {
        month: '2026-08',
        employee_count: 2,
        closed: 1,
        submitted: 0,
        open: 1,
        exports: [{ kind: 'CSV', date_from: '2026-08-01', date_to: '2026-08-31', employee_count: 2, created_at: '2026-09-02T10:15:00', created_by: 'hr@example.com' }],
      },
    })
    renderWithProviders(<PayrollExportPage />)
    fireEvent.change(screen.getByLabelText('Monat'), { target: { value: '2026-08' } })
    expect(await screen.findByText(/1 von 2 abgeschlossen, 1 offen/)).toBeInTheDocument()
    expect(screen.getByText(/können sich die Werte noch ändern/)).toBeInTheDocument()
    expect(screen.getByText(/Schon exportiert: CSV am .* von hr@example.com/)).toBeInTheDocument()
    await waitFor(() => {
      const call = calls.filter((c) => c.path === '/payroll-export/status').at(-1)
      expect(call?.init.params?.query).toEqual({ month: '2026-08', employee_ids: [1, 2] })
    })
  })
})
