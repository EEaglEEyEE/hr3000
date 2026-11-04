/** Tarifanzeige: Karte in den Einstellungen und Hinweis in der Mitarbeiterliste. */
import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../../test/utils'
import { PlanCard, PlanNotice } from './PlanNotice'

function plan(overrides: Record<string, unknown> = {}) {
  return { plan: 'FREE', active_employees: 3, limit: 5, remaining: 2, ...overrides }
}

describe('Tarif', () => {
  it('zeigt die Auslastung des kostenlosen Tarifs', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /plan': plan() })
    renderWithProviders(<PlanCard />)
    expect(await screen.findByText(/Kostenlos für bis zu 5 aktive Mitarbeiter/)).toHaveTextContent(
      'Ab 6 aktiven Mitarbeitern kostet jeder aktive Mitarbeiter 1 € im Monat (z. B. 6 Mitarbeiter = 6 €)',
    )
    expect(screen.getByText(/von 5 aktive Mitarbeiter/)).toHaveTextContent('3 von 5 aktive Mitarbeiter')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3')
  })

  it('zeigt bei Abo und Unbegrenzt keine Grenze', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /plan': plan({ plan: 'UNLIMITED', active_employees: 42, limit: null, remaining: null }) })
    renderWithProviders(<PlanCard />)
    expect(await screen.findByText(/Unbegrenzt – ohne Mitarbeitergrenze/)).toBeInTheDocument()
    expect(screen.getByText(/aktive Mitarbeiter$/)).toHaveTextContent('42 aktive Mitarbeiter')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it.each([
    { remaining: 2, text: null },
    { remaining: 1, text: 'Noch ein Mitarbeiter frei.' },
    { remaining: 0, text: 'Weitere Mitarbeiter lassen sich nur mit Abo aktivieren' },
  ])('Hinweis in der Mitarbeiterliste bei $remaining freien Plätzen', async ({ remaining, text }) => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({ 'GET /plan': plan({ remaining, active_employees: 5 - remaining }) })
    const { container } = renderWithProviders(<PlanNotice />)
    await waitFor(() => expect(calls.some((call) => call.path === '/plan')).toBe(true))
    if (text) {
      expect(await screen.findByText(new RegExp(text))).toBeInTheDocument()
    } else {
      await new Promise((r) => setTimeout(r, 50))
      expect(container).toBeEmptyDOMElement()
    }
  })

  it('kein Hinweis bei bezahltem Tarif', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    mockApi({ 'GET /plan': plan({ plan: 'PAID', active_employees: 30, limit: null, remaining: null }) })
    const { container } = renderWithProviders(<PlanNotice />)
    await new Promise((r) => setTimeout(r, 50))
    expect(container).toBeEmptyDOMElement()
  })
})
