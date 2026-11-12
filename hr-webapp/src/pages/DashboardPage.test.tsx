/** Startseite: Konten mit eigener Rolle ohne Tagesgeschäft landen direkt in der Lohnbuchhaltung. */
import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders } from '../test/utils'
import { DashboardPage } from './DashboardPage'

function renderStart() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/lohnbuchhaltung" element={<p>Lohnbuchhaltung-Seite</p>} />
    </Routes>,
  )
}

describe('Startseite mit eigener Rolle', () => {
  it('leitet das Lohnbüro zur Lohnbuchhaltung', async () => {
    loginAs({ kind: 'hr', role: 'HR', payroll: true, perms: { PAYROLL: 'VIEW' } })
    mockApi({ 'GET /features': { shift_planning_enabled: false, payroll_accounting_enabled: true } })
    renderStart()
    expect(await screen.findByText('Lohnbuchhaltung-Seite')).toBeInTheDocument()
  })

  it('zeigt einen Hinweis, wenn die Lohnbuchhaltung aus ist', async () => {
    loginAs({ kind: 'hr', role: 'HR', payroll: true, perms: { PAYROLL: 'VIEW' } })
    mockApi({ 'GET /features': { shift_planning_enabled: false, payroll_accounting_enabled: false } })
    renderStart()
    expect(await screen.findByText('Ihrer Rolle ist noch kein Bereich freigegeben.')).toBeInTheDocument()
  })
})
