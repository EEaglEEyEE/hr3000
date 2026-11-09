/** „Zu klären“ als Posteingang: Reiter für Tage, Korrekturanträge, Urlaubsanträge und Grenzen. */
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { hrTodoRoutes, openDay } from '../test/fixtures'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { OpenDaysPage } from './OpenDaysPage'

function renderInbox(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/zu-klaeren/:reiter?" element={<OpenDaysPage />} />
    </Routes>,
    { route },
  )
}

const absence = {
  id: 9,
  employee_id: 3,
  type: 'VACATION',
  absence_type_id: null,
  date_from: '2026-12-21',
  date_to: '2026-12-23',
  half_day: false,
  duration_minutes: null,
}

describe('Zu klären (Posteingang)', () => {
  it('zeigt Reiter mit Anzahl und öffnet Urlaubsanträge über die Adresse', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      ...hrTodoRoutes({ openDays: [openDay(1, '2026-10-19')], pendingAbsences: [absence], corrections: [] }),
      'GET /locations': [],
      'GET /employees': [{ id: 3, first_name: 'Erika', last_name: 'Muster' }],
      'GET /absence-types': [],
    })
    renderInbox('/zu-klaeren/urlaubsantraege')
    expect(await screen.findByText('Erika Muster')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Genehmigen' })).toBeInTheDocument()
    const tabs = screen.getAllByRole('tab').map((tab) => tab.textContent)
    expect(tabs).toEqual(['Tage1', 'Korrekturanträge', 'Urlaubsanträge1', 'Grenzen', 'Datenänderungen'])

    await userEvent.click(screen.getByRole('tab', { name: /Grenzen/ }))
    expect(await screen.findByText(/Keine Aushilfe „nach Aufwand“/)).toBeInTheDocument()
  })

  it('zeigt Überstundenkonten an den Grenzen unter „Grenzen“', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({
      ...hrTodoRoutes({
        limits: [{ employee_id: 3, first_name: 'Erika', last_name: 'Muster', balance_minutes: 1260, limit_minutes: 1200, kind: 'MAX', exceeded: true }],
      }),
      'GET /locations': [],
    })
    renderInbox('/zu-klaeren/monatsgrenzen')
    expect(await screen.findByText(/Obergrenze \+20:00 Std\. überschritten/)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Grenzen/ })).toHaveTextContent('Grenzen1')
  })

  it('zeigt Führungskräfte keine Korrekturanträge und startet mit den Tagen', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi({ ...hrTodoRoutes({ openDays: [openDay(1, '2026-10-19')] }), 'GET /locations': [] })
    renderInbox('/zu-klaeren')
    const tablist = await screen.findByRole('tablist')
    expect(within(tablist).queryByRole('tab', { name: /Korrekturanträge/ })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Tage/ })).toHaveAttribute('aria-selected', 'true')
  })
})
