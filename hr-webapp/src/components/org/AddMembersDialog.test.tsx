/** Mitarbeiter im Organigramm einer Abteilung hinzufügen (mehrere auf einmal, mit Suche). */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { OrgChart } from './OrgChart'

type Leader = { employee_id: number; role: 'HEAD' | 'DEPUTY'; deputy_rights: 'STANDBY' | 'FULL' | 'ABSENCE' }
const person = (id: number, first: string, department: number | null, position: string | null = null) => ({
  employee_id: id, first_name: first, last_name: 'Test', position, department_id: department,
  department: null, supervisor_ids: [] as number[],
})
const dep = (id: number, name: string, parent: number | null, leaders: Leader[] = []) => ({ id, name, parent_id: parent, leaders })

// Geschäftsführung (Leitung Bea) → Vertrieb (Leitungen Erika und Nora, Stellvertretung Ute: Max) → Innendienst (Tief)
//                                → Lager (leer)
// Solo und Nora ohne Abteilung
const ORG = {
  departments: [
    dep(1, 'Geschäftsführung', null, [{ employee_id: 1, role: 'HEAD', deputy_rights: 'STANDBY' }]),
    dep(2, 'Vertrieb', 1, [
      { employee_id: 2, role: 'HEAD', deputy_rights: 'STANDBY' },
      { employee_id: 7, role: 'HEAD', deputy_rights: 'STANDBY' },
      { employee_id: 5, role: 'DEPUTY', deputy_rights: 'FULL' },
    ]),
    dep(3, 'Innendienst', 2),
    dep(4, 'Lager', 1),
  ],
  people: [
    person(1, 'Bea', 1, 'Geschäftsführerin'),
    person(2, 'Erika', 2),
    person(3, 'Max', 2, 'Außendienst'),
    person(5, 'Ute', 2),
    person(6, 'Tief', 3),
    person(4, 'Solo', null),
    person(7, 'Nora', null),
  ],
}

const MEMBERS_PATH = '/departments/{department_id}/members'

function routes(extra: Record<string, unknown> = {}) {
  return {
    'GET /org-chart': ORG,
    'GET /departments': [],
    [`POST ${MEMBERS_PATH}`]: { department: { id: 4, name: 'Lager', parent_id: 1, leaders: [], employee_count: 2 }, added: 2 },
    ...extra,
  }
}

const posts = (calls: ApiCall[]) => calls.filter((c) => c.method === 'POST' && c.path === MEMBERS_PATH)

async function open(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: `Mitarbeiter zu ${name} hinzufügen` }))
  return screen.findByRole('dialog')
}

const group = (dialog: HTMLElement, title: RegExp) => within(dialog).getByRole('region', { name: title })
const names = (section: HTMLElement) =>
  within(section)
    .getAllByRole('checkbox')
    .map((box) => box.closest('label')?.querySelector('span span')?.textContent)

describe('Mitarbeiter zu einer Abteilung hinzufügen', () => {
  afterEach(() => vi.restoreAllMocks())

  it('zeigt zuerst wer ohne Abteilung ist, dann wer wechselt – mit bisheriger Abteilung und Position', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes())
    renderWithProviders(<OrgChart />)
    const dialog = await open('Lager')
    expect(within(dialog).getByRole('heading', { name: 'Mitarbeiter zu Lager hinzufügen' })).toBeInTheDocument()
    const none = group(dialog, /^Ohne Abteilung/)
    expect(names(none)).toEqual(['Solo Test', 'Nora Test'])
    const other = group(dialog, /^Aus anderen Abteilungen/)
    expect(names(other)).toEqual(['Bea Test', 'Erika Test', 'Max Test', 'Ute Test', 'Tief Test'])
    expect(within(other).getByText('Außendienst · bisher Geschäftsführung › Vertrieb')).toBeInTheDocument()
    expect(within(other).getByText('bisher Geschäftsführung › Vertrieb › Innendienst')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Hinzufügen' })).toBeDisabled()
  })

  it('nimmt mehrere auf einmal auf – in Listen-Reihenfolge – und schließt danach', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(routes())
    renderWithProviders(<OrgChart />)
    const dialog = await open('Lager')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Solo Test/ }))
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Max Test/ }))
    const loadsBefore = calls.filter((c) => c.path === '/org-chart').length
    await userEvent.click(within(dialog).getByRole('button', { name: '2 hinzufügen' }))
    await waitFor(() =>
      expect(posts(calls).at(-1)?.init).toMatchObject({
        params: { path: { department_id: 4 } },
        body: { employee_ids: [3, 4] },
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(calls.filter((c) => c.path === '/org-chart').length).toBeGreaterThan(loadsBefore)) // neu geladen
  })

  it('lässt Mitglieder weg und kennzeichnet Leitungen der Abteilung', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes())
    renderWithProviders(<OrgChart />)
    const dialog = await open('Vertrieb')
    expect(names(group(dialog, /^Ohne Abteilung/))).toEqual(['Solo Test', 'Nora Test'])
    expect(within(dialog).getByText('leitet diese Abteilung')).toBeInTheDocument()
    expect(names(group(dialog, /^Aus anderen Abteilungen/))).toEqual(['Bea Test', 'Tief Test']) // Erika, Max, Ute sind schon drin
  })

  it('kennzeichnet Stellvertretungen der Abteilung, die woanders arbeiten', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(
      routes({
        'GET /org-chart': {
          departments: [dep(1, 'A', null, [{ employee_id: 9, role: 'DEPUTY', deputy_rights: 'ABSENCE' }]), dep(2, 'B', null)],
          people: [person(9, 'Vize', 2)],
        },
      }),
    )
    renderWithProviders(<OrgChart />)
    const dialog = await open('A')
    expect(within(dialog).getByText('bisher B · Stellvertretung hier')).toBeInTheDocument()
  })

  it('sucht nach Name, Position und Abteilung – Gewählte bleiben gewählt', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes())
    renderWithProviders(<OrgChart />)
    const dialog = await open('Lager')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Solo Test/ }))
    const search = within(dialog).getByRole('textbox', { name: 'Mitarbeiter suchen' })

    await userEvent.type(search, 'außen')
    expect(within(dialog).getAllByRole('checkbox')).toHaveLength(1)
    expect(within(dialog).getByRole('checkbox', { name: /Max Test/ })).toBeInTheDocument()
    expect(within(dialog).queryByRole('region', { name: /^Ohne Abteilung/ })).not.toBeInTheDocument()

    await userEvent.clear(search)
    await userEvent.type(search, 'innendienst')
    expect(names(group(dialog, /^Aus anderen/))).toEqual(['Tief Test'])

    await userEvent.clear(search)
    await userEvent.type(search, 'xyz')
    expect(within(dialog).getByText('Niemand gefunden.')).toBeInTheDocument()

    // Solo ist ausgeblendet, aber weiter gewählt
    await userEvent.click(within(dialog).getByRole('button', { name: '1 hinzufügen' }))
    await waitFor(() => expect(posts(calls).at(-1)?.init.body).toEqual({ employee_ids: [4] }))
  })

  it('wählt eine ganze Gruppe aus und wieder ab, einzelne lassen sich abwählen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes())
    renderWithProviders(<OrgChart />)
    const dialog = await open('Lager')
    const none = group(dialog, /^Ohne Abteilung/)
    await userEvent.click(within(none).getByRole('button', { name: 'Alle auswählen' }))
    expect(within(none).getAllByRole('checkbox').every((box) => (box as HTMLInputElement).checked)).toBe(true)
    expect(within(dialog).getByRole('button', { name: '2 hinzufügen' })).toBeEnabled()
    await userEvent.click(within(none).getByRole('button', { name: 'Keine auswählen' }))
    expect(within(dialog).getByRole('button', { name: 'Hinzufügen' })).toBeDisabled()

    await userEvent.click(within(none).getByRole('button', { name: 'Alle auswählen' }))
    await userEvent.click(within(none).getByRole('checkbox', { name: /Nora Test/ })) // wieder abwählen
    expect(within(none).getByRole('button', { name: 'Alle auswählen' })).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: '1 hinzufügen' }))
    await waitFor(() => expect(posts(calls).at(-1)?.init.body).toEqual({ employee_ids: [4] }))
  })

  it('zeigt Fehler im Dialog und bleibt offen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(
      routes({
        [`POST ${MEMBERS_PATH}`]: new ApiFailure(400, 'SUPERVISOR_CYCLE', 'Damit wäre Bea Test (indirekt) die eigene Führungskraft.'),
      }),
    )
    renderWithProviders(<OrgChart />)
    const dialog = await open('Lager')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Bea Test/ }))
    await userEvent.click(within(dialog).getByRole('button', { name: '1 hinzufügen' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('die eigene Führungskraft')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('meldet unerwartete Fehler allgemein', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(
      routes({
        [`POST ${MEMBERS_PATH}`]: () => {
          throw new Error('Netzwerk weg')
        },
      }),
    )
    renderWithProviders(<OrgChart />)
    const dialog = await open('Lager')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Solo Test/ }))
    await userEvent.click(within(dialog).getByRole('button', { name: '1 hinzufügen' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Hinzufügen fehlgeschlagen.')
  })

  it('sagt es, wenn schon alle in der Abteilung sind', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(routes({ 'GET /org-chart': { departments: [dep(1, 'Alle', null)], people: [person(1, 'Eine', 1), person(2, 'Zwei', 1)] } }))
    renderWithProviders(<OrgChart />)
    const dialog = await open('Alle')
    expect(within(dialog).getByText('Alle aktiven Mitarbeiter sind schon in dieser Abteilung.')).toBeInTheDocument()
    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Hinzufügen' })).toBeDisabled()
  })

  it('beginnt für jede Abteilung neu und schließt ohne Änderung über Abbrechen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(routes())
    renderWithProviders(<OrgChart />)
    let dialog = await open('Lager')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Solo Test/ }))
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Mitarbeiter suchen' }), 'so')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Abbrechen' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    dialog = await open('Innendienst')
    expect(within(dialog).getByRole('textbox', { name: 'Mitarbeiter suchen' })).toHaveValue('')
    expect(within(dialog).getByRole('checkbox', { name: /Solo Test/ })).not.toBeChecked()
    expect(within(dialog).getByRole('button', { name: 'Hinzufügen' })).toBeDisabled()
    expect(posts(calls)).toHaveLength(0)
  })

  it('gibt es nur für Admin und HR', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    mockApi(routes())
    renderWithProviders(<OrgChart />)
    await screen.findByRole('group', { name: 'Abteilung Lager' })
    expect(screen.queryByRole('button', { name: /^Mitarbeiter zu .* hinzufügen$/ })).not.toBeInTheDocument()
  })
})
