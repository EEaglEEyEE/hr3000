/** Dokument aus Vorlage in die Akte legen. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { DocumentsTab } from './DocumentsTab'

describe('Dokumentvorlagen', () => {
  it('legt ein Dokument aus der gewählten Vorlage an', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi({
      'GET /employees/{employee_id}/documents': [],
      'GET /document-categories': [],
      'GET /document-templates': [
        { id: 1, name: 'Arbeitsbescheinigung', body: 'x', category: 'CERTIFICATE', category_id: null, employee_visible: true, archived: false },
        { id: 2, name: 'Alt', body: 'x', category: 'OTHER', category_id: null, employee_visible: false, archived: true },
      ],
      'POST /employees/{employee_id}/documents/from-template': { id: 9 },
    })
    renderWithProviders(<DocumentsTab employeeId={7} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Aus Vorlage erstellen' }))
    expect(screen.queryByRole('option', { name: 'Alt' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'In die Akte legen' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.init.body).toEqual({ template_id: 1, title: null }),
    )
  })
})
