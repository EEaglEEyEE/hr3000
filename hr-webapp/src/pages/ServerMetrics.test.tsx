/** Super-Admin → „Server“: aktuelle Auslastung, Verlauf je Kennzahl, Zeitraum umschaltbar. */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { loginAs, mockApi, renderWithProviders, type ApiInit } from '../test/utils'
import { ServerMetricsPage } from './ServerMetricsPage'

const GB = 1024 ** 3

function metrics(overrides: Record<string, unknown> = {}) {
  const now = Date.now()
  return {
    range: '24h',
    bucket_minutes: 5,
    interval_seconds: 60,
    retention_days: 30,
    current: {
      cpu_count: 4,
      cpu_percent: 12.4,
      load_1: 0.52,
      load_5: 0.4,
      load_15: 0.31,
      memory_used_bytes: 7.4 * GB,
      memory_total_bytes: 8 * GB,
      disk_used_bytes: 30 * GB,
      disk_total_bytes: 80 * GB,
      uptime_seconds: 3 * 86400 + 4 * 3600,
    },
    points: [20, 15, 10].map((minutes, i) => ({
      at: new Date(now - minutes * 60_000).toISOString(),
      cpu_percent: 10 + i * 10,
      cpu_max_percent: 50 + i,
      memory_percent: 40,
      disk_percent: 37.5,
      load_1: 0.5,
    })),
    ...overrides,
  }
}

describe('Super-Admin: Server-Auslastung', () => {
  it('zeigt aktuelle Werte mit Hinweis ab 90 % und je Kennzahl einen Verlauf', async () => {
    loginAs({ kind: 'hr', role: 'SUPER_ADMIN' })
    mockApi({ 'GET /platform/server-metrics': metrics() })
    renderWithProviders(<ServerMetricsPage />)
    expect(await screen.findByText('12 %')).toBeInTheDocument()
    expect(screen.getAllByText('4 Kerne')).toHaveLength(2) // Kachel und Bezugslinie bei der Last
    expect(screen.getByText('7,4 GB von 8,0 GB')).toBeInTheDocument()
    expect(screen.getByText('93 %')).toBeInTheDocument() // Arbeitsspeicher
    expect(screen.getAllByText('hoch')).toHaveLength(1)
    expect(screen.getByText('3 Tage 4 Std.')).toBeInTheDocument()
    for (const title of ['CPU (%)', 'Arbeitsspeicher (%)', 'Datenträger (%)', 'Last (1 Min.)']) {
      expect(screen.getByRole('img', { name: title })).toBeInTheDocument()
    }
    // Tabellenansicht mit allen Punkten (neueste zuerst), CPU mit Spitzenwert
    const cpu = screen.getByRole('img', { name: 'CPU (%)' }).closest('figure')!
    const rows = within(cpu).getAllByRole('row')
    expect(rows).toHaveLength(4)
    expect(rows[1]).toHaveTextContent('30 % (Spitze 52 %)')
  })

  it('zeigt beim Überfahren und per Pfeiltaste einen Tooltip', async () => {
    loginAs({ kind: 'hr', role: 'SUPER_ADMIN' })
    mockApi({ 'GET /platform/server-metrics': metrics() })
    renderWithProviders(<ServerMetricsPage />)
    const chart = await screen.findByRole('img', { name: 'CPU (%)' })
    chart.focus()
    fireEvent.keyDown(chart, { key: 'ArrowLeft' })
    const tooltip = await within(chart.closest('figure')!).findByRole('status')
    expect(tooltip).toHaveTextContent('20 %')
    expect(tooltip).toHaveTextContent('Spitze 51 %')
  })

  it('fragt beim Wechsel des Zeitraums den passenden Verlauf ab', async () => {
    loginAs({ kind: 'hr', role: 'SUPER_ADMIN' })
    const calls = mockApi({
      'GET /platform/server-metrics': (init: ApiInit) => metrics({ range: init.params?.query?.range, bucket_minutes: 60 }),
    })
    renderWithProviders(<ServerMetricsPage />)
    await screen.findByText('12 %')
    await userEvent.click(screen.getByRole('button', { name: '7 Tage' }))
    await waitFor(() => expect(calls.some((c) => c.init.params?.query?.range === '7d')).toBe(true))
    expect(screen.getByRole('button', { name: '7 Tage' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('erklärt, wenn der Server keine Werte liefert', async () => {
    loginAs({ kind: 'hr', role: 'SUPER_ADMIN' })
    mockApi({ 'GET /platform/server-metrics': metrics({ current: null, points: [] }) })
    renderWithProviders(<ServerMetricsPage />)
    expect(await screen.findByText(/liefert keine Messwerte/)).toBeInTheDocument()
    expect(screen.getAllByText('Keine Messwerte im Zeitraum.')).toHaveLength(4)
  })
})
