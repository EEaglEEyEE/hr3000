/** Schalter „Zeiterfassung“ im Mitarbeiterformular: Standard an, blendet Tablet-Angaben aus, wird gesendet. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { employee } from '../../test/fixtures'
import { loginAs, mockApi, renderWithProviders, type ApiCall, type ApiInit } from '../../test/utils'
import { EmployeeForm, EmployeeFormDialog } from './EmployeeFormDialog'

const LOCATIONS = [{ id: 1, name: 'Zentrale', timezone: 'Europe/Berlin' }] as never

const FEATURES = {
  shift_planning_enabled: false,
  absence_requests_enabled: true,
  default_auto_break: true,
  default_show_birthday: true,
  default_day_minutes: null,
}

function api(extra: Record<string, unknown> = {}) {
  return mockApi({
    'GET /features': FEATURES,
    'GET /departments': [],
    'GET /employees': [],
    'POST /employees': (init: ApiInit) => ({ id: 9, ...(init.body as object) }),
    'PATCH /employees/{employee_id}': (init: ApiInit) => employee({ id: 5, ...(init.body as object) }),
    ...extra,
  })
}

function body(calls: ApiCall[], method: 'POST' | 'PATCH') {
  return calls.find((call) => call.method === method)?.init.body as Record<string, unknown> | undefined
}

async function fillBasics() {
  await userEvent.type(screen.getByLabelText('Vorname'), 'Paula')
  await userEvent.type(screen.getByLabelText('Nachname'), 'Probe')
  await userEvent.type(screen.getByLabelText(/Personalnummer/), 'P1')
}

const switchBox = () => screen.getByRole('checkbox', { name: 'Zeiterfassung' })

afterEach(() => vi.restoreAllMocks())

describe('Neuer Mitarbeiter: „Zeiterfassung“', () => {
  it('ist standardmäßig an und wird mitgesendet', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api()
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    expect(switchBox()).toBeChecked()
    expect(screen.getByText(/Aus: kein Stempeln, kein Soll und kein Gleitzeitkonto/)).toBeInTheDocument()
    expect(screen.getByText(/Weitere Angaben \(.*Zeiterfassung/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(body(calls, 'POST')).toMatchObject({ time_tracking: true }))
  })

  it('zeigt mit Zeiterfassung PIN, Chip und „Pausen automatisch stempeln“', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api()
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await screen.findByLabelText('Vorname')
    expect(screen.getByLabelText('PIN (optional)')).toBeInTheDocument()
    expect(screen.getByLabelText('Chip-UID (optional)')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Pausen automatisch stempeln/ })).toBeInTheDocument()
    expect(screen.getByText('Login und Stempeln am Tablet (E-Mail, Passwort, PIN, Chip)')).toBeInTheDocument()
    expect(screen.queryByText(/erscheint der Mitarbeiter nicht am Tablet/)).not.toBeInTheDocument()
  })

  it('blendet ohne Zeiterfassung Tablet-Angaben und Pausen aus, Login bleibt', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api()
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await screen.findByLabelText('Vorname')
    await userEvent.click(switchBox())
    expect(switchBox()).not.toBeChecked()
    expect(screen.queryByLabelText('PIN (optional)')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Chip-UID (optional)')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /Pausen automatisch stempeln/ })).not.toBeInTheDocument()
    expect(screen.getByText(/erscheint der Mitarbeiter nicht am Tablet/)).toBeInTheDocument()
    expect(screen.getByText('Login (E-Mail, Passwort)')).toBeInTheDocument()
    expect(screen.getByLabelText('Login-E-Mail')).toBeInTheDocument()
    // Beim Anlegen gibt es nichts rückwirkend zu ändern
    expect(screen.queryByText(/Gilt rückwirkend/)).not.toBeInTheDocument()
  })

  it('sendet time_tracking: false und lässt sich wieder einschalten', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api()
    renderWithProviders(<EmployeeFormDialog open onOpenChange={vi.fn()} locations={LOCATIONS} />)
    await fillBasics()
    await userEvent.click(switchBox())
    await userEvent.click(switchBox())
    expect(screen.getByLabelText('PIN (optional)')).toBeInTheDocument()
    await userEvent.click(switchBox())
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(body(calls, 'POST')).toMatchObject({ time_tracking: false }))
  })
})

describe('Mitarbeiter bearbeiten: „Zeiterfassung“', () => {
  it('übernimmt den gespeicherten Stand (aus)', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api()
    renderWithProviders(<EmployeeForm employee={employee({ time_tracking: false })} locations={LOCATIONS} />)
    await waitFor(() => expect(switchBox()).not.toBeChecked())
    expect(screen.queryByLabelText(/PIN/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Gilt rückwirkend/)).not.toBeInTheDocument()
  })

  it('wertet ein fehlendes Feld (ältere Antwort) als an', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api()
    const legacy = employee()
    delete (legacy as Partial<typeof legacy>).time_tracking
    renderWithProviders(<EmployeeForm employee={legacy} locations={LOCATIONS} />)
    await waitFor(() => expect(switchBox()).toBeChecked())
    expect(screen.queryByText(/Gilt rückwirkend/)).not.toBeInTheDocument()
  })

  it('weist beim Ausschalten auf die rückwirkende Wirkung hin und speichert', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api()
    renderWithProviders(<EmployeeForm employee={employee({ time_tracking: true })} locations={LOCATIONS} />)
    await waitFor(() => expect(switchBox()).toBeChecked())
    await userEvent.click(switchBox())
    expect(screen.getByText(/Gilt rückwirkend .* Stempelungen zählen nicht mehr/)).toBeInTheDocument()
    expect(screen.getByText(/Abgeschlossene Monate bleiben unverändert/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(body(calls, 'PATCH')).toMatchObject({ time_tracking: false }))
    expect(await screen.findByText('Gespeichert.')).toBeInTheDocument()
  })

  it('weist beim Einschalten darauf hin, dass das Konto neu berechnet wird', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = api()
    renderWithProviders(<EmployeeForm employee={employee({ time_tracking: false })} locations={LOCATIONS} />)
    await waitFor(() => expect(switchBox()).not.toBeChecked())
    await userEvent.click(switchBox())
    expect(screen.getByText(/Stempelungen zählen wieder, das Gleitzeitkonto wird neu berechnet/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Neuer PIN/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(body(calls, 'PATCH')).toMatchObject({ time_tracking: true }))
  })

  it('setzt den Schalter mit „Änderungen verwerfen“ zurück', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api()
    renderWithProviders(<EmployeeForm employee={employee({ time_tracking: true })} locations={LOCATIONS} />)
    await waitFor(() => expect(switchBox()).toBeChecked())
    await userEvent.click(switchBox())
    await userEvent.click(screen.getByRole('button', { name: 'Änderungen verwerfen' }))
    expect(switchBox()).toBeChecked()
    expect(screen.queryByText(/Gilt rückwirkend/)).not.toBeInTheDocument()
  })

  it('lädt nach dem Umschalten Startseite, „Zu klären“, Monatsabschluss und Übersichten neu', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    api()
    const { queryClient } = renderWithProviders(
      <EmployeeForm employee={employee({ time_tracking: true })} locations={LOCATIONS} />,
    )
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    await waitFor(() => expect(switchBox()).toBeChecked())
    await userEvent.click(switchBox())
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await screen.findByText('Gespeichert.')
    const keys = invalidate.mock.calls.map(([filters]) => (filters as { queryKey: string[] }).queryKey[0])
    expect(keys).toEqual(
      expect.arrayContaining(['employees', 'open-days', 'dashboard', 'period-closures', 'timesheet-overview', 'balance-limits', 'monthly-caps']),
    )
  })
})
