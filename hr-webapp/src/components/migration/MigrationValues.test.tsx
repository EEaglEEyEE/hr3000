/** Migration: Werte aus dem Altsystem – erst Vorschau, dann übernehmen. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, renderWithProviders } from '../../test/utils'
import { MigrationValuesSection } from './MigrationValuesSection'

const preview = {
  applied: false,
  rows: [{ row: 2, employee_id: 1, employee_number: '100', name: 'Alt, Anna', changes: ['Gleitzeit-Übertrag +12,5 h', 'Urlaubsanspruch 30 Tage'] }],
  errors: [{ row: 3, message: "Personalnummer '999' nicht gefunden." }],
}

afterEach(() => vi.restoreAllMocks())

describe('Werte aus dem Altsystem', () => {
  it('zeigt die Vorschau und übernimmt danach', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(preview), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...preview, applied: true }), { status: 200 }))
    renderWithProviders(<MigrationValuesSection />)

    expect(screen.getByRole('button', { name: 'Übernehmen' })).toBeDisabled()
    const cutover = screen.getByLabelText('Stichtag')
    await userEvent.clear(cutover)
    await userEvent.type(cutover, '2026-10-01')
    const file = new File(['personalnummer;saldo_stunden\n100;12,5\n'], 'alt.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByLabelText('CSV-Datei mit Werten aus dem Altsystem'), file)
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau' }))

    expect(await screen.findByText(/Vorschau: 1 Mitarbeiter/)).toBeInTheDocument()
    expect(screen.getByText('Gleitzeit-Übertrag +12,5 h · Urlaubsanspruch 30 Tage')).toBeInTheDocument()
    expect(screen.getByText("Personalnummer '999' nicht gefunden.")).toBeInTheDocument()
    const firstBody = fetchMock.mock.calls[0][1]?.body as FormData
    expect(firstBody.get('apply')).toBe('false')
    expect(firstBody.get('cutover')).toBe('2026-10-01')

    await userEvent.click(screen.getByRole('button', { name: 'Übernehmen' }))
    expect(await screen.findByText(/Werte für 1 Mitarbeiter zum 1\.10\.2026 übernommen/)).toBeInTheDocument()
    await waitFor(() => expect((fetchMock.mock.calls[1][1]?.body as FormData).get('apply')).toBe('true'))
    expect(screen.getByRole('button', { name: 'Übernehmen' })).toBeDisabled()
  })
})
