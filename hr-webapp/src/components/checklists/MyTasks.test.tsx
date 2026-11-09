/** „Meine Aufgaben“: abhaken und Upload-Aufgabe mit Datei erledigen. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { MyTasks } from './MyTasks'

const base = { position: 0, description: null, responsible: 'EMPLOYEE', due_date: '2026-11-20', done: false, done_at: null, note: null }

afterEach(() => vi.restoreAllMocks())

describe('Meine Aufgaben', () => {
  it('hakt ab und lädt für Upload-Aufgaben direkt hoch', async () => {
    loginAs({ kind: 'employee', employeeId: 7 })
    const calls = mockApi({
      'GET /me/checklist-items': [
        { ...base, id: 1, title: 'Hausordnung lesen', action: 'TASK', action_category_id: null },
        { ...base, id: 2, title: 'Führerschein', action: 'UPLOAD_DOCUMENT', action_category_id: 3 },
      ],
      'POST /me/checklist-items/{item_id}/done': { ...base, id: 1, title: 'Hausordnung lesen', done: true },
    })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 201 }))
    renderWithProviders(<MyTasks employeeId={7} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Erledigt' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/me/checklist-items/{item_id}/done')).toBe(true))
    await userEvent.upload(screen.getByLabelText('Datei für Führerschein'), new File(['%PDF'], 'f.pdf', { type: 'application/pdf' }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const form = (fetchSpy.mock.calls[0][1] as RequestInit).body as FormData
    expect([form.get('category_id'), form.get('checklist_item_id')]).toEqual(['3', '2'])
  })
})
