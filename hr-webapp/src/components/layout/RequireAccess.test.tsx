import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { loginAs, renderWithProviders } from '../../test/utils'
import { RequireAccess } from './RequireAccess'

describe('Seitenschutz', () => {
  it('lässt HR ohne eigene Rolle auf die Seite', () => {
    loginAs({ kind: 'hr', role: 'HR' })
    renderWithProviders(<RequireAccess path="/monatsabschluss"><p>Seite</p></RequireAccess>)
    expect(screen.getByText('Seite')).toBeInTheDocument()
  })

  it('sperrt Seiten außerhalb der Bereiche einer eigenen Rolle', () => {
    loginAs({ kind: 'hr', role: 'HR', perms: { TIME: 'VIEW' } })
    renderWithProviders(<RequireAccess path="/monatsabschluss"><p>Seite</p></RequireAccess>)
    expect(screen.getByText('Für diese Seite fehlt die Berechtigung.')).toBeInTheDocument()
  })

  it('erlaubt Seiten im freigegebenen Bereich', () => {
    loginAs({ kind: 'hr', role: 'HR', perms: { PERIOD_CLOSURE: 'VIEW' } })
    renderWithProviders(<RequireAccess path="/monatsabschluss"><p>Seite</p></RequireAccess>)
    expect(screen.getByText('Seite')).toBeInTheDocument()
  })

  it('ignoriert perms bei Admins (Admins haben keine eigene Rolle)', () => {
    loginAs({ kind: 'hr', role: 'ADMIN', perms: { TIME: 'VIEW' } })
    renderWithProviders(<RequireAccess path="/monatsabschluss"><p>Seite</p></RequireAccess>)
    expect(screen.getByText('Seite')).toBeInTheDocument()
  })

  it('wertet unbekannte Stufen als kein Zugriff', () => {
    loginAs({ kind: 'hr', role: 'HR', perms: { PERIOD_CLOSURE: 'SUPER' as never } })
    renderWithProviders(<RequireAccess path="/monatsabschluss"><p>Seite</p></RequireAccess>)
    expect(screen.queryByText('Seite')).not.toBeInTheDocument()
  })
})
