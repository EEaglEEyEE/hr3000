/** Eigene Dokumentkategorien: Name in der Liste und Upload durch Mitarbeiter. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { DocumentsTab } from './DocumentsTab'

const doc = {
  id: 1, employee_id: 7, category: 'OTHER', category_id: 3, title: 'Erste Hilfe', original_filename: 'kurs.pdf',
  content_type: 'application/pdf', size_bytes: 1200, confidential: false, employee_visible: true, retention_until: null,
  created_at: '2026-11-07T10:00:00',
}

afterEach(() => vi.restoreAllMocks())

describe('Dokumentkategorien', () => {
  it('zeigt den Namen der eigenen Kategorie und lädt als Mitarbeiter hoch', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    mockApi({
      'GET /employees/{employee_id}/documents': [doc],
      'GET /document-categories': [{ id: 3, name: 'Bescheinigungen', employee_upload: true, employee_visible: true, confidential: false, archived: false }],
    })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(doc), { status: 201 }))
    renderWithProviders(<DocumentsTab employeeId={7} readOnly />)
    expect(await screen.findByText('Bescheinigungen')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Dokument hochladen/ }))
    await userEvent.upload(screen.getByLabelText(/Datei/), new File(['%PDF'], 'zeugnis.pdf', { type: 'application/pdf' }))
    await userEvent.type(screen.getByLabelText('Titel'), 'Zeugnis')
    await userEvent.click(screen.getByRole('button', { name: 'Hochladen' }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe('/api/me/documents')
    const form = (init as RequestInit).body as FormData
    expect([form.get('category_id'), form.get('title')]).toEqual(['3', 'Zeugnis'])
  })
})
