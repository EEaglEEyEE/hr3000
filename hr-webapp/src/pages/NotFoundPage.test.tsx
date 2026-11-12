import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { NotFoundPage } from './NotFoundPage'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<p>Startseite</p>} />
        <Route path="mitarbeiter" element={<p>Mitarbeiterliste</p>} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('NotFoundPage', () => {
  it('zeigt bei unbekannter Adresse einen Hinweis statt einer leeren Seite', () => {
    renderAt('/mitarbeiter/1')
    expect(screen.getByRole('heading', { name: 'Seite nicht gefunden' })).toBeInTheDocument()
    expect(screen.getByText('/mitarbeiter/1')).toBeInTheDocument()
  })

  it('verlinkt zur Startseite', () => {
    renderAt('/gibt-es-nicht')
    expect(screen.getByRole('link', { name: 'Zur Startseite' })).toHaveAttribute('href', '/')
  })

  it('greift nicht bei bekannten Adressen', () => {
    renderAt('/mitarbeiter')
    expect(screen.getByText('Mitarbeiterliste')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Seite nicht gefunden' })).not.toBeInTheDocument()
  })

  it('zeigt auch tief verschachtelte Adressen vollständig an', () => {
    renderAt('/a/b/c/d')
    expect(screen.getByText('/a/b/c/d')).toBeInTheDocument()
  })
})
