/** Bedienelemente am Tablet: richtige Stempel-Buttons je Einstellung, PIN-Eingabe,
 * RFID-Terminalleiste und Mitarbeiterraster (Anwesenheit, Suche, Offline-Anzeige). */
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { employee, queued } from '../test/fixtures'
import { EmployeeGrid } from './EmployeeGrid'
import { PinPad } from './PinPad'
import { PunchPad } from './PunchPad'
import { TerminalBar } from './TerminalBar'

const ALL = ['Kommen', 'Gehen', 'Pause Start', 'Pause Ende', 'Dienstgang Start', 'Dienstgang Ende']

function punchButtonLabels(): string[] {
  return screen
    .getAllByRole('button')
    .map((button) => button.textContent ?? '')
    .filter((label) => ALL.includes(label))
}

describe('PunchPad', () => {
  function renderPad(props: Partial<Parameters<typeof PunchPad>[0]> = {}) {
    const onPunch = vi.fn()
    const onCancel = vi.fn()
    render(
      <PunchPad employee={employee()} isSubmitting={false} error={null} balance={null} leaveEntitlement={null} onPunch={onPunch} onCancel={onCancel} {...props} />,
    )
    return { onPunch, onCancel }
  }

  it.each([
    { breakButtons: true, errandButtons: true, expected: ALL },
    { breakButtons: false, errandButtons: true, expected: ['Kommen', 'Gehen', 'Dienstgang Start', 'Dienstgang Ende'] },
    { breakButtons: true, errandButtons: false, expected: ['Kommen', 'Gehen', 'Pause Start', 'Pause Ende'] },
    { breakButtons: false, errandButtons: false, expected: ['Kommen', 'Gehen'] },
  ])('Pause=$breakButtons, Dienstgang=$errandButtons -> $expected', ({ breakButtons, errandButtons, expected }) => {
    renderPad({ breakButtons, errandButtons })
    expect(punchButtonLabels()).toEqual(expected)
  })

  it('meldet die gewählte Stempelart', async () => {
    const { onPunch } = renderPad()
    await userEvent.click(screen.getByRole('button', { name: 'Dienstgang Start' }))
    expect(onPunch).toHaveBeenCalledWith('ERRAND_START')
  })

  it('sperrt alle Knöpfe während des Sendens', async () => {
    const { onPunch, onCancel } = renderPad({ isSubmitting: true, onRegisterCard: vi.fn() })
    for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Kommen' }))
    expect(onPunch).not.toHaveBeenCalled()
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('zeigt Saldo, Resturlaub, Fehler und Identifizierung an', () => {
    renderPad({
      balance: { employee_id: 1, balance_date: '2026-10-20', running_balance_minutes: -75 },
      leaveEntitlement: { employee_id: 1, year: 2026, entitled_days: 30, carried_over_days: 0, used_days: 17.5, remaining_days: 12.5 },
      error: 'PIN falsch.',
      identifiedViaCard: true,
    })
    expect(screen.getByText('Gleitzeitsaldo: -1:15 Std.')).toBeInTheDocument()
    expect(screen.getByText('Resturlaub: 12,5 Tage')).toBeInTheDocument()
    expect(screen.getByText('PIN falsch.')).toBeInTheDocument()
    expect(screen.getByText('Per Karte identifiziert')).toBeInTheDocument()
  })

  it('bietet die Chip-Registrierung nur an, wenn sie erlaubt ist', () => {
    renderPad()
    expect(screen.queryByRole('button', { name: 'Eigenen Chip registrieren' })).not.toBeInTheDocument()
  })
})

describe('PinPad', () => {
  function renderPinPad(props: Partial<Parameters<typeof PinPad>[0]> = {}) {
    const onSubmit = vi.fn()
    render(<PinPad employee={employee()} isSubmitting={false} error={null} onSubmit={onSubmit} onCancel={vi.fn()} {...props} />)
    return { onSubmit }
  }

  async function press(...keys: string[]) {
    for (const key of keys) await userEvent.click(screen.getByRole('button', { name: key }))
  }

  it('sendet die eingegebene PIN, ⌫ löscht die letzte Ziffer', async () => {
    const { onSubmit } = renderPinPad()
    await press('1', '2', '9', '⌫', '3', '4')
    await press('Bestätigen')
    expect(onSubmit).toHaveBeenCalledWith('1234')
  })

  it('erlaubt höchstens 8 Ziffern', async () => {
    const { onSubmit } = renderPinPad()
    await press(...'1234567890'.split(''))
    await press('Bestätigen')
    expect(onSubmit).toHaveBeenCalledWith('12345678')
  })

  it('lässt "Bestätigen" erst ab der Mindestlänge zu (neuen PIN festlegen)', async () => {
    renderPinPad({ minLength: 4, title: 'Neuen PIN festlegen' })
    expect(screen.getByText('Neuen PIN festlegen')).toBeInTheDocument()
    await press('1', '2', '3')
    expect(screen.getByRole('button', { name: 'Bestätigen' })).toBeDisabled()
    await press('4')
    expect(screen.getByRole('button', { name: 'Bestätigen' })).toBeEnabled()
  })

  it('löschen bei leerer Eingabe schadet nicht', async () => {
    const { onSubmit } = renderPinPad()
    await press('⌫', '⌫', '5')
    await press('Bestätigen')
    expect(onSubmit).toHaveBeenCalledWith('5')
  })

  it('nimmt während der Prüfung keine Eingaben an', async () => {
    renderPinPad({ isSubmitting: true })
    expect(screen.getByRole('button', { name: '1' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Prüfe…' })).toBeDisabled()
  })
})

describe('TerminalBar (Chip-Terminal)', () => {
  it('blendet Pause/Dienstgang je Einstellung aus', () => {
    render(<TerminalBar armed={null} armedUntil={0} onArm={vi.fn()} onDisarm={vi.fn()} result={null} breakButtons={false} errandButtons={false} />)
    expect(punchButtonLabels()).toEqual(['Kommen', 'Gehen'])
  })

  it('wählt eine Aktion und hebt sie mit erneutem Tippen wieder auf', async () => {
    const onArm = vi.fn()
    const onDisarm = vi.fn()
    const { rerender } = render(<TerminalBar armed={null} armedUntil={0} onArm={onArm} onDisarm={onDisarm} result={null} />)
    await userEvent.click(screen.getByRole('button', { name: 'Gehen' }))
    expect(onArm).toHaveBeenCalledWith('GO')

    rerender(<TerminalBar armed="GO" armedUntil={Date.now() + 10_000} onArm={onArm} onDisarm={onDisarm} result={null} />)
    await userEvent.click(screen.getByRole('button', { name: 'Gehen' }))
    expect(onDisarm).toHaveBeenCalled()
  })

  it('zählt die verbleibenden Sekunden herunter und bleibt bei 0 stehen', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-21T08:00:00Z'))
    render(<TerminalBar armed="COME" armedUntil={Date.now() + 10_000} onArm={vi.fn()} onDisarm={vi.fn()} result={null} />)
    expect(screen.getByText(/„Kommen“ gewählt – jetzt Chip vorhalten \(10 s\)/)).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(4_000))
    expect(screen.getByText(/\(6 s\)/)).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(20_000))
    expect(screen.getByText(/\(0 s\)/)).toBeInTheDocument()
  })

  it('zeigt Erfolg und Fehler unterschiedlich an', () => {
    const { rerender } = render(
      <TerminalBar armed={null} armedUntil={0} onArm={vi.fn()} onDisarm={vi.fn()} result={{ ok: true, title: 'Erika Muster', detail: 'Kommen 08:00' }} />,
    )
    expect(screen.getByText('Erika Muster').parentElement).toHaveClass('bg-emerald-900')
    rerender(<TerminalBar armed={null} armedUntil={0} onArm={vi.fn()} onDisarm={vi.fn()} result={{ ok: false, title: 'Chip unbekannt' }} />)
    expect(screen.getByText('Chip unbekannt').parentElement).toHaveClass('bg-red-900')
  })
})

describe('Mitarbeiterraster', () => {
  const PEOPLE = [
    employee({ id: 1, first_name: 'Erika', last_name: 'Muster', today_status: 'PRESENT' }),
    employee({ id: 2, first_name: 'Max', last_name: 'Beispiel', today_status: 'ON_BREAK' }),
    employee({ id: 3, first_name: 'Anna', last_name: 'Zeit', today_status: 'ON_ERRAND' }),
    employee({ id: 4, first_name: 'Ben', last_name: 'Älter', today_status: 'COMPLETE' }),
    employee({ id: 5, first_name: 'Carl', last_name: 'Offen', today_status: 'ERROR' }),
  ]

  function renderGrid(props: Partial<Parameters<typeof EmployeeGrid>[0]> = {}) {
    const onSelect = vi.fn()
    const onRegisterCard = vi.fn()
    render(
      <EmployeeGrid
        employees={PEOPLE}
        deviceName="Test-Tablet"
        isLoading={false}
        error={null}
        isOnline
        queuedPunches={[]}
        onDiscardQueuedPunch={vi.fn()}
        selectionError={null}
        nfcSupported={false}
        nfcActive={false}
        nfcError={null}
        onToggleNfc={vi.fn()}
        onSelect={onSelect}
        onReset={vi.fn(async () => {})}
        {...props}
      />,
    )
    return { onSelect, onRegisterCard }
  }

  function tile(lastName: string) {
    return screen.getByText(lastName).closest('button') as HTMLElement
  }

  it('zeigt Anwesend/Pause/Dienstgang, alles andere als Abwesend', () => {
    renderGrid()
    expect(within(tile('Muster')).getByText('Anwesend')).toBeInTheDocument()
    expect(within(tile('Beispiel')).getByText('Pause')).toBeInTheDocument()
    expect(within(tile('Zeit')).getByText('Dienstgang')).toBeInTheDocument()
    expect(tile('Zeit')).toHaveClass('border-violet-500')
    expect(within(tile('Älter')).getByText('Abwesend')).toBeInTheDocument()
    expect(within(tile('Offen')).getByText('Abwesend')).toBeInTheDocument()
  })

  it('sortiert nach Nachname (mit Umlauten richtig) oder Vorname', () => {
    renderGrid()
    const order = () => screen.getAllByRole('button').map((b) => b.textContent).filter((t) => /Abwesend|Anwesend|Pause|Dienstgang/.test(t ?? '') && !/Online/.test(t ?? ''))
    expect(order().map((t) => t?.replace(/(Anwesend|Abwesend|Pause|Dienstgang)$/, ''))).toEqual([
      'BenÄlter',
      'MaxBeispiel',
      'ErikaMuster',
      'CarlOffen',
      'AnnaZeit',
    ])
  })

  it('sucht nach Vor- und Nachname, ohne Groß/Kleinschreibung', async () => {
    renderGrid()
    await userEvent.type(screen.getByPlaceholderText('Name suchen…'), 'erika m')
    expect(screen.getByText('Muster')).toBeInTheDocument()
    expect(screen.queryByText('Beispiel')).not.toBeInTheDocument()
    await userEvent.clear(screen.getByPlaceholderText('Name suchen…'))
    await userEvent.type(screen.getByPlaceholderText('Name suchen…'), 'niemand')
    expect(screen.getByText('Keine Mitarbeiter gefunden.')).toBeInTheDocument()
  })

  it('öffnet beim Antippen den Mitarbeiter – bei Chip-Pflicht nur die Chip-Registrierung', async () => {
    const { onSelect } = renderGrid()
    await userEvent.click(tile('Muster'))
    expect(onSelect).toHaveBeenCalledWith(PEOPLE[0])
  })

  it('löst bei Chip-Pflicht ohne Registrierung beim Antippen nichts aus', async () => {
    const onRegisterCard = vi.fn()
    const { onSelect } = renderGrid({ rfidRequired: true })
    await userEvent.click(tile('Muster'))
    expect(onSelect).not.toHaveBeenCalled()
    expect(onRegisterCard).not.toHaveBeenCalled()
    expect(screen.getByText(/Stempeln nur mit Chip/)).toBeInTheDocument()
  })

  it('führt bei Chip-Pflicht mit erlaubter Registrierung dorthin', async () => {
    const onRegisterCard = vi.fn()
    const { onSelect } = renderGrid({ rfidRequired: true, onRegisterCard })
    await userEvent.click(tile('Muster'))
    expect(onSelect).not.toHaveBeenCalled()
    expect(onRegisterCard).toHaveBeenCalledWith(PEOPLE[0])
  })

  it('zeigt offline die Anzahl wartender Stempelungen und deren Fehler', async () => {
    const onDiscard = vi.fn()
    renderGrid({
      isOnline: false,
      queuedPunches: [queued('a'), queued('b', { punch_type: 'ERRAND_START', error: 'PIN falsch.' })],
      onDiscardQueuedPunch: onDiscard,
    })
    const status = screen.getByRole('button', { name: /Offline/ })
    expect(status).toHaveTextContent('2')
    await userEvent.click(status)
    expect(screen.getByText('Erika Muster – Dienstgang Start')).toBeInTheDocument()
    expect(screen.getByText('Fehler: PIN falsch.')).toBeInTheDocument()
    // Nur fehlerhafte Einträge können verworfen werden.
    const discard = screen.getAllByRole('button', { name: 'Verwerfen' })
    expect(discard).toHaveLength(1)
    await userEvent.click(discard[0])
    expect(onDiscard).toHaveBeenCalledWith('b')
  })

  it('setzt das Gerät nur mit mindestens 4-stelliger Admin-PIN zurück und zeigt Fehler', async () => {
    const onReset = vi.fn(async () => {
      throw new Error('Admin-PIN falsch.')
    })
    renderGrid({ onReset })
    await userEvent.click(screen.getByRole('button', { name: 'Gerät zurücksetzen' }))
    const input = screen.getByPlaceholderText('Admin-PIN')
    await userEvent.type(input, '12a3')
    expect(input).toHaveValue('123') // nur Ziffern
    expect(screen.getByRole('button', { name: 'Zurücksetzen' })).toBeDisabled()
    await userEvent.type(input, '4')
    await userEvent.click(screen.getByRole('button', { name: 'Zurücksetzen' }))
    expect(onReset).toHaveBeenCalledWith('1234')
    expect(await screen.findByText('Admin-PIN falsch.')).toBeInTheDocument()
    expect(input).toHaveValue('') // PIN wird nach dem Versuch geleert
  })
})
