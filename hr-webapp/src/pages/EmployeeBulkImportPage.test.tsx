/** Mitarbeiter-Import: die Seite nennt alle Spalten, die der Import versteht – auch Turnus und
 * abgegoltene Überstunden. */
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { EmployeeBulkImportPage } from './EmployeeBulkImportPage'

function setup() {
  loginAs({ kind: 'hr', role: 'HR' })
  mockApi({
    'GET /locations': [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }],
    'GET /departments': [],
    'GET /migration/values': [],
  })
  renderWithProviders(<EmployeeBulkImportPage />)
}

describe('Mitarbeiter-Import', () => {
  it.each(['tagesstunden_woche2', 'tagesstunden_woche3', 'tagesstunden_woche4', 'turnus_beginn', 'abgegoltene_ueberstunden'])(
    'nennt die Spalte %s',
    async (column) => {
      setup()
      expect(await screen.findByText(new RegExp(`(^|, )${column}(,|$)`))).toBeInTheDocument()
    },
  )

  it('erklärt Turnus und abgegoltene Überstunden', async () => {
    setup()
    expect(await screen.findByText(/Mehrwöchiges Modell \(Turnus über 2 bis 4 Wochen\)/)).toBeInTheDocument()
    expect(screen.getByText(/nur zusammen mit einem Arbeitszeitmodell in derselben Zeile/)).toBeInTheDocument()
  })

  it('nennt weiter die Pflichtspalten', async () => {
    setup()
    expect(await screen.findByText('vorname, nachname, personalnummer, standort')).toBeInTheDocument()
  })
})
