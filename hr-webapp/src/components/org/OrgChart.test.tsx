/** Organigramm als Abteilungsbaum (Leitungen, Stellvertretungen, Mitarbeiter, Unterabteilungen), direkt
 *  bearbeitbar für Admin und HR (Dialoge, Verschieben, Ziehen), und die Abteilungsseite. */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DepartmentsPage } from '../../pages/DepartmentsPage'
import { buildOrgTree, subtreeIds, type OrgLeader } from '../../lib/orgTree'
import { employee } from '../../test/fixtures'
import { ApiFailure, loginAs, mockApi, renderWithProviders, type ApiCall } from '../../test/utils'
import { OrgChart } from './OrgChart'

const person = (id: number, first: string, department: number | null, position: string | null = null) => ({
  employee_id: id, first_name: first, last_name: 'Test', position, department_id: department,
  department: null, supervisor_ids: [] as number[],
})
const head = (id: number): OrgLeader => ({ employee_id: id, role: 'HEAD', deputy_rights: 'STANDBY' })
const deputy = (id: number, rights: OrgLeader['deputy_rights'] = 'STANDBY'): OrgLeader => ({ employee_id: id, role: 'DEPUTY', deputy_rights: rights })
const dep = (id: number, name: string, parent: number | null, leaders: OrgLeader[] = []) => ({ id, name, parent_id: parent, leaders })

// Geschäftsführung (Leitung Bea) → Vertrieb (Leitungen Erika und Nora, Stellvertretung Ute mit vollen Rechten: Max)
//                                     → Innendienst (ohne Leitung: Tief)
//                                 → Lager (ohne Leitung, leer)
// Solo ohne Abteilung; Nora leitet den Vertrieb, ohne selbst einer Abteilung anzugehören
const ORG = {
  departments: [
    dep(1, 'Geschäftsführung', null, [head(1)]),
    dep(2, 'Vertrieb', 1, [head(2), head(7), deputy(5, 'FULL')]),
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

// Abteilungen mit Namen der Leitungen (GET /departments, für den Bearbeiten-Dialog)
const leader = (id: number, name: string, role: 'HEAD' | 'DEPUTY', rights: OrgLeader['deputy_rights'] = 'STANDBY', active = true) => ({
  employee_id: id, name, role, deputy_rights: rights, active,
})
const DEPARTMENTS = [
  { id: 1, name: 'Geschäftsführung', parent_id: null, leaders: [leader(1, 'Bea Test', 'HEAD')], employee_count: 1 },
  {
    id: 2, name: 'Vertrieb', parent_id: 1, employee_count: 3,
    leaders: [leader(2, 'Erika Test', 'HEAD'), leader(7, 'Nora Test', 'HEAD'), leader(5, 'Ute Test', 'DEPUTY', 'FULL')],
  },
  { id: 3, name: 'Innendienst', parent_id: 2, leaders: [], employee_count: 1 },
  { id: 4, name: 'Lager', parent_id: 1, leaders: [], employee_count: 0 },
]
const EMPLOYEES = [
  employee({ id: 1, first_name: 'Bea', last_name: 'Test' }),
  employee({ id: 2, first_name: 'Erika', last_name: 'Test' }),
  employee({ id: 3, first_name: 'Max', last_name: 'Test' }),
  employee({ id: 5, first_name: 'Ute', last_name: 'Test' }),
  employee({ id: 7, first_name: 'Nora', last_name: 'Test' }),
]

function editRoutes(extra: Record<string, unknown> = {}) {
  return {
    'GET /org-chart': ORG,
    'GET /departments': DEPARTMENTS,
    'GET /employees': EMPLOYEES,
    'PATCH /departments/{department_id}': DEPARTMENTS[1],
    'POST /departments': { ...DEPARTMENTS[3], id: 9, name: 'Neu' },
    'DELETE /departments/{department_id}': null,
    'PATCH /employees/{employee_id}': employee({ id: 3 }),
    ...extra,
  }
}

const last = (calls: ApiCall[], method: string, path?: string) =>
  calls.filter((c) => c.method === method && (path === undefined || c.path === path)).at(-1)

async function choose(label: string, option: string) {
  await userEvent.click(screen.getByRole('combobox', { name: label }))
  await userEvent.click(await screen.findByRole('option', { name: option }))
}

const card = (name: string) => screen.getByRole('group', { name: `Abteilung ${name}` })

function dataTransfer() {
  return { setData: vi.fn(), getData: vi.fn(), effectAllowed: '', dropEffect: '' }
}

function drag(source: HTMLElement, target: HTMLElement) {
  const transfer = dataTransfer()
  fireEvent.dragStart(source, { dataTransfer: transfer })
  fireEvent.dragOver(target, { dataTransfer: transfer })
  fireEvent.drop(target, { dataTransfer: transfer })
  fireEvent.dragEnd(source, { dataTransfer: transfer })
  return transfer
}

describe('Abteilungsbaum (Logik)', () => {
  it('ordnet Leitungen, Stellvertretungen, Mitarbeiter und Unterabteilungen zu und zählt den Bereich', () => {
    const { roots, unassigned } = buildOrgTree(ORG.departments, ORG.people)
    expect(roots.map((r) => r.department.name)).toEqual(['Geschäftsführung'])
    const gf = roots[0]
    expect(gf.heads.map((h) => h.first_name)).toEqual(['Bea'])
    expect(gf.members).toEqual([]) // Bea ist Leitung, nicht nochmal Mitarbeiterin
    expect(gf.children.map((c) => c.department.name)).toEqual(['Lager', 'Vertrieb']) // alphabetisch
    const sales = gf.children[1]
    expect(sales.heads.map((h) => h.first_name)).toEqual(['Erika', 'Nora']) // Reihenfolge wie eingetragen
    expect(sales.deputies.map((d) => [d.person.first_name, d.rights])).toEqual([['Ute', 'FULL']])
    expect(sales.members.map((m) => m.first_name)).toEqual(['Max']) // ohne Leitungen und Stellvertretung
    expect(sales.size).toBe(5) // Erika, Nora, Ute, Max + Tief darunter
    expect(gf.size).toBe(6)
    expect(unassigned.map((p) => p.first_name)).toEqual(['Solo']) // Nora leitet, steht also nicht „ohne Abteilung“
  })

  it('übersteht Leitungen ohne Abteilung, verwaiste Verweise und Kreise', () => {
    const headElsewhere = buildOrgTree(
      [dep(1, 'A', null, [head(9), deputy(8, 'ABSENCE')])],
      [person(9, 'Chefin', null), person(8, 'Vize', null), person(6, 'Ohne', null)],
    )
    expect(headElsewhere.roots[0].heads.map((h) => h.first_name)).toEqual(['Chefin'])
    expect(headElsewhere.roots[0].deputies.map((d) => d.person.first_name)).toEqual(['Vize'])
    expect(headElsewhere.unassigned.map((p) => p.first_name)).toEqual(['Ohne'])
    expect(buildOrgTree([dep(1, 'A', 99)], []).roots.map((r) => r.department.name)).toEqual(['A'])
    expect(buildOrgTree([dep(1, 'A', 2), dep(2, 'B', 1)], []).roots).toEqual([]) // Kreis ohne Wurzel: kein Absturz
    const unknown = buildOrgTree([dep(1, 'A', null, [head(77), deputy(78)])], [])
    expect(unknown.roots[0].heads).toEqual([])
    expect(unknown.roots[0].deputies).toEqual([])
  })

  it('findet eine Abteilung samt allem darunter', () => {
    expect([...subtreeIds(ORG.departments, 2)].sort()).toEqual([2, 3])
    expect([...subtreeIds(ORG.departments, 1)].sort()).toEqual([1, 2, 3, 4])
    expect([...subtreeIds(ORG.departments, 4)]).toEqual([4])
  })
})

describe('Organigramm', () => {
  afterEach(() => vi.restoreAllMocks())

  it('zeigt den Abteilungsbaum mit Leitungen, Stellvertretung und Mitarbeitern, ohne Abteilung darunter', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /org-chart': ORG })
    renderWithProviders(<OrgChart />)
    const tree = await screen.findByRole('group', { name: 'Baum Geschäftsführung' })
    expect(screen.getByRole('button', { name: 'Baum' })).toHaveAttribute('aria-pressed', 'true')
    expect(tree).toHaveClass('org-tree')
    expect(within(tree).getByText('Bea Test')).toBeInTheDocument()
    const sales = card('Vertrieb')
    expect(sales.closest('li')).toHaveClass('org-node')
    expect(sales).toHaveTextContent('Leitungen: Erika Test, Nora Test')
    expect(sales).toHaveTextContent('Stellvertretung: Ute Test (gleiche Rechte)')
    expect(within(sales).getByText('Max Test')).toBeInTheDocument()
    expect(within(sales).getByText(/Außendienst/)).toBeInTheDocument()
    expect(card('Geschäftsführung')).toHaveTextContent('Leitung: Bea Test')
    expect(card('Lager')).toHaveTextContent('ohne Leitung')
    const singles = screen.getByRole('region', { name: 'Ohne Abteilung' })
    expect(within(singles).getByText('Solo Test')).toBeInTheDocument()
    expect(within(singles).queryByText('Nora Test')).not.toBeInTheDocument()
  })

  it('klappt Unterabteilungen und Mitarbeiterlisten auf und zu', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const many = [...ORG.people, ...[8, 9, 10, 11].map((id) => person(id, `Neu${id}`, 2))] // Vertrieb: 5 Mitarbeiter
    mockApi({ 'GET /org-chart': { ...ORG, people: many } })
    renderWithProviders(<OrgChart />)
    const tree = await screen.findByRole('group', { name: 'Baum Geschäftsführung' })
    // mehr als vier Mitarbeiter: Liste anfangs zu
    const membersButton = within(tree).getByRole('button', { name: /5 Mitarbeiter/ })
    expect(membersButton).toHaveAttribute('aria-expanded', 'false')
    expect(within(tree).queryByText('Neu8 Test')).not.toBeInTheDocument()
    await userEvent.click(membersButton)
    expect(within(tree).getByText('Neu8 Test')).toBeInTheDocument()
    // dritte Ebene (Innendienst) ist offen, Unterabteilungen lassen sich zuklappen
    await userEvent.click(within(tree).getByRole('button', { name: 'Unterabteilungen von Vertrieb zuklappen' }))
    expect(within(tree).queryByText('Innendienst')).not.toBeInTheDocument()
    await userEvent.click(within(tree).getByRole('button', { name: 'Unterabteilungen von Vertrieb aufklappen' }))
    expect(within(tree).getByText('Innendienst')).toBeInTheDocument()
  })

  it('sucht nach Abteilung, Person (auch Leitung und Stellvertretung) und Position und markiert Treffer', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /org-chart': ORG })
    renderWithProviders(<OrgChart />)
    const search = await screen.findByLabelText('Im Organigramm suchen')
    await userEvent.type(search, 'tief')
    const tree = screen.getByRole('group', { name: 'Baum Geschäftsführung' })
    expect(within(tree).getByText('Tief Test').closest('li')).toHaveClass('text-sky-700')
    expect(within(tree).queryByText('Lager')).not.toBeInTheDocument() // ohne Treffer ausgeblendet
    expect(screen.queryByRole('region', { name: 'Ohne Abteilung' })).not.toBeInTheDocument()
    await userEvent.clear(search)
    await userEvent.type(search, 'ute')
    expect(within(card('Vertrieb')).getByText('Ute Test')).toHaveClass('text-sky-700')
    await userEvent.clear(search)
    await userEvent.type(search, 'nora')
    expect(within(card('Vertrieb')).getByText('Nora Test')).toHaveClass('text-sky-700')
    await userEvent.clear(search)
    await userEvent.type(search, 'solo')
    expect(screen.queryByRole('group', { name: 'Baum Geschäftsführung' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Ohne Abteilung' })).getByText('Solo Test')).toBeInTheDocument()
    await userEvent.clear(search)
    await userEvent.type(search, 'lager')
    expect(card('Lager')).toHaveClass('border-sky-500')
    await userEvent.clear(search)
    await userEvent.type(search, 'niemand')
    expect(screen.getByText('Nichts gefunden.')).toBeInTheDocument()
  })

  it('zeigt einen Hinweis, solange es nichts gibt', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /org-chart': { departments: [], people: [] } })
    renderWithProviders(<OrgChart />)
    expect(await screen.findByText('Noch keine Abteilungen oder Mitarbeiter.')).toBeInTheDocument()
  })

  it('merkt sich die Darstellung und startet am Handy mit der Liste', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /org-chart': ORG })
    const { unmount } = renderWithProviders(<OrgChart />)
    await userEvent.click(await screen.findByRole('button', { name: 'Liste' }))
    expect(screen.queryByRole('group', { name: 'Baum Geschäftsführung' })).not.toBeInTheDocument()
    expect(card('Vertrieb')).toBeInTheDocument() // Liste zeigt dieselben Abteilungen
    await userEvent.click(screen.getByRole('button', { name: 'Unterabteilungen von Geschäftsführung zuklappen' }))
    expect(screen.queryByRole('group', { name: 'Abteilung Vertrieb' })).not.toBeInTheDocument()
    expect(localStorage.getItem('hr3000.orgchart.view')).toBe('list')
    unmount()
    renderWithProviders(<OrgChart />)
    expect(await screen.findByRole('button', { name: 'Liste' })).toHaveAttribute('aria-pressed', 'true')
    unmount()

    localStorage.clear()
    loginAs({ kind: 'hr', role: 'HR' })
    vi.spyOn(window, 'matchMedia').mockImplementation(
      (media: string) => ({ matches: media.includes('max-width'), media }) as unknown as MediaQueryList,
    )
    renderWithProviders(<OrgChart />)
    expect(await screen.findByRole('button', { name: 'Liste' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('funktioniert auch ohne Speicher im Browser', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi({ 'GET /org-chart': ORG })
    // nur der Speicher des Organigramms ist gesperrt (Anmeldung & Co. bleiben unberührt)
    const getItem = Storage.prototype.getItem
    const setItem = Storage.prototype.setItem
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (this: Storage, key: string) {
      if (key === 'hr3000.orgchart.view') throw new Error('blocked')
      return getItem.call(this, key)
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key: string, value: string) {
      if (key === 'hr3000.orgchart.view') throw new Error('blocked')
      setItem.call(this, key, value)
    })
    renderWithProviders(<OrgChart />)
    await userEvent.click(await screen.findByRole('button', { name: 'Liste' }))
    expect(screen.getByRole('button', { name: 'Liste' })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('Organigramm bearbeiten', () => {
  afterEach(() => vi.restoreAllMocks())

  it('zeigt Führungskräften keine Bearbeiten-Möglichkeiten', async () => {
    loginAs({ kind: 'hr', role: 'SUPERVISOR' })
    const calls = mockApi(editRoutes())
    renderWithProviders(<OrgChart />)
    await screen.findByRole('group', { name: 'Abteilung Vertrieb' })
    expect(screen.queryByRole('button', { name: 'Vertrieb bearbeiten' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Max Test verschieben' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Neue Abteilung/ })).not.toBeInTheDocument()
    expect(card('Vertrieb')).not.toHaveAttribute('draggable')
    expect(calls.some((c) => c.path === '/departments')).toBe(false) // lädt die Abteilungsliste gar nicht erst
  })

  it('bearbeitet Leitungen und Stellvertretungen einer Abteilung direkt im Organigramm', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(editRoutes())
    renderWithProviders(<OrgChart />)
    await userEvent.click(await screen.findByRole('button', { name: 'Vertrieb bearbeiten' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Vertrieb')
    expect(within(dialog).getByText('Nora Test')).toBeInTheDocument()
    // Nora wird Stellvertretung „nur bei Abwesenheit“, Ute fliegt raus
    await choose('Rolle von Nora Test', 'Stellvertretung')
    await choose('Rechte von Nora Test', 'Nur während Abwesenheit der Leitung')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Ute Test entfernen' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(last(calls, 'PATCH', '/departments/{department_id}')?.init).toMatchObject({
        params: { path: { department_id: 2 } },
        body: {
          name: 'Vertrieb',
          parent_id: 1,
          clear_parent_id: false,
          leaders: [
            { employee_id: 2, role: 'HEAD', deputy_rights: 'STANDBY' },
            { employee_id: 7, role: 'DEPUTY', deputy_rights: 'ABSENCE' },
          ],
        },
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('legt eine Unterabteilung unter der gewählten an und über die Leiste eine oberste', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi(editRoutes())
    renderWithProviders(<OrgChart />)
    await userEvent.click(await screen.findByRole('button', { name: 'Unterabteilung zu Vertrieb anlegen' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Neue Abteilung' })).toBeInTheDocument()
    expect(within(dialog).getByRole('combobox', { name: 'Übergeordnete Abteilung' })).toHaveTextContent('Vertrieb')
    await userEvent.type(within(dialog).getByLabelText('Name'), 'Außendienst')
    await choose('Person hinzufügen', 'Test, Max')
    expect(within(dialog).getByRole('combobox', { name: 'Rolle von Max Test' })).toHaveTextContent('Leitung') // erste = Leitung
    await choose('Person hinzufügen', 'Test, Bea')
    expect(within(dialog).getByRole('combobox', { name: 'Rolle von Bea Test' })).toHaveTextContent('Stellvertretung')
    expect(within(dialog).getByText(/Entscheidet und wird benachrichtigt, wenn keine Leitung da ist/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(last(calls, 'POST', '/departments')?.init.body).toEqual({
        name: 'Außendienst',
        parent_id: 2,
        leaders: [
          { employee_id: 3, role: 'HEAD', deputy_rights: 'STANDBY' },
          { employee_id: 1, role: 'DEPUTY', deputy_rights: 'STANDBY' },
        ],
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: /Neue Abteilung/ }))
    await userEvent.type(within(await screen.findByRole('dialog')).getByLabelText('Name'), 'Werk 2')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(last(calls, 'POST', '/departments')?.init.body).toEqual({ name: 'Werk 2', parent_id: null, leaders: [] }))
  })

  it('löscht eine Abteilung nur nach Rückfrage und zeigt den Grund, wenn es nicht geht', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(
      editRoutes({
        'DELETE /departments/{department_id}': (init: { params?: { path?: { department_id?: number } } }) =>
          init.params?.path?.department_id === 4
            ? null
            : new ApiFailure(409, 'DEPARTMENT_IN_USE', 'Die Abteilung hat noch Mitarbeiter oder Unterabteilungen.'),
      }),
    )
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true)
    renderWithProviders(<OrgChart />)
    await userEvent.click(await screen.findByRole('button', { name: 'Lager löschen' }))
    expect(confirm).toHaveBeenCalledWith('Abteilung „Lager“ löschen? Das geht nur, wenn sie leer ist.')
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Lager löschen' }))
    await waitFor(() => expect(last(calls, 'DELETE')?.init).toMatchObject({ params: { path: { department_id: 4 } } }))
    await userEvent.click(screen.getByRole('button', { name: 'Vertrieb löschen' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Die Abteilung hat noch Mitarbeiter oder Unterabteilungen.')
  })

  it('verschiebt eine Person per Dialog in eine andere Abteilung oder heraus', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(editRoutes())
    renderWithProviders(<OrgChart />)
    await userEvent.click(await screen.findByRole('button', { name: 'Max Test verschieben' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('combobox', { name: 'Abteilung' })).toHaveTextContent('Geschäftsführung › Vertrieb')
    await choose('Abteilung', 'Geschäftsführung › Lager')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Verschieben' }))
    await waitFor(() =>
      expect(last(calls, 'PATCH', '/employees/{employee_id}')?.init).toMatchObject({
        params: { path: { employee_id: 3 } },
        body: { department_id: 4, clear_department_id: false, clear_supervisor_id: false },
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Solo Test verschieben' }))
    expect(within(await screen.findByRole('dialog')).getByRole('combobox', { name: 'Abteilung' })).toHaveTextContent('– ohne Abteilung –')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Abbrechen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Max Test verschieben' }))
    await choose('Abteilung', '– ohne Abteilung –')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Verschieben' }))
    await waitFor(() =>
      expect(last(calls, 'PATCH', '/employees/{employee_id}')?.init.body).toMatchObject({ department_id: null, clear_department_id: true }),
    )
  })

  it('zeigt Fehler beim Verschieben im Dialog', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(editRoutes({ 'PATCH /employees/{employee_id}': new ApiFailure(400, 'SUPERVISOR_CYCLE', 'Damit wäre Max Test (indirekt) die eigene Führungskraft.') }))
    renderWithProviders(<OrgChart />)
    await userEvent.click(await screen.findByRole('button', { name: 'Max Test verschieben' }))
    await choose('Abteilung', 'Geschäftsführung › Lager')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Verschieben' }))
    expect(await within(screen.getByRole('dialog')).findByText(/die eigene Führungskraft/)).toBeInTheDocument()
  })

  it('zieht Personen auf Abteilungen und aus Abteilungen heraus', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(editRoutes())
    renderWithProviders(<OrgChart />)
    const max = (await screen.findByText('Max Test')).closest('li')!
    expect(max).toHaveAttribute('draggable', 'true')
    const transfer = drag(max, card('Lager'))
    expect(transfer.setData).toHaveBeenCalledWith('application/x-hr3000-org', JSON.stringify({ kind: 'person', id: 3 }))
    await waitFor(() =>
      expect(last(calls, 'PATCH', '/employees/{employee_id}')?.init).toMatchObject({
        params: { path: { employee_id: 3 } },
        body: { department_id: 4, clear_department_id: false },
      }),
    )
    // heraus: „Ohne Abteilung“ nimmt beim Ziehen Personen an
    const before = calls.filter((c) => c.method === 'PATCH').length
    fireEvent.dragStart(screen.getByText('Max Test').closest('li')!, { dataTransfer: dataTransfer() })
    const singles = screen.getByRole('region', { name: 'Ohne Abteilung' })
    fireEvent.dragOver(singles)
    fireEvent.drop(singles)
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH').length).toBeGreaterThan(before))
    expect(last(calls, 'PATCH', '/employees/{employee_id}')?.init.body).toMatchObject({ clear_department_id: true })
  })

  it('nimmt eine Person in ihrer eigenen Abteilung nicht an', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(editRoutes())
    renderWithProviders(<OrgChart />)
    const max = (await screen.findByText('Max Test')).closest('li')!
    fireEvent.dragStart(max, { dataTransfer: dataTransfer() })
    expect(card('Vertrieb')).not.toHaveAttribute('data-drop-target')
    expect(card('Lager')).toHaveAttribute('data-drop-target', 'true')
    fireEvent.drop(card('Vertrieb'))
    fireEvent.dragEnd(max)
    expect(card('Lager')).not.toHaveAttribute('data-drop-target')
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
  })

  it('hängt Abteilungen per Ziehen um – nie unter sich selbst, auf Wunsch auf die oberste Ebene', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    const calls = mockApi(editRoutes())
    renderWithProviders(<OrgChart />)
    const sales = await screen.findByRole('group', { name: 'Abteilung Vertrieb' })
    fireEvent.dragStart(sales, { dataTransfer: dataTransfer() })
    expect(card('Innendienst')).not.toHaveAttribute('data-drop-target') // darunter: ginge im Kreis
    expect(card('Geschäftsführung')).not.toHaveAttribute('data-drop-target') // hängt schon dort
    expect(card('Lager')).toHaveAttribute('data-drop-target', 'true')
    const top = screen.getByLabelText('Oberste Ebene')
    fireEvent.dragOver(top)
    fireEvent.drop(top)
    await waitFor(() =>
      expect(last(calls, 'PATCH', '/departments/{department_id}')?.init).toMatchObject({
        params: { path: { department_id: 2 } },
        body: { clear_parent_id: true },
      }),
    )
    expect(screen.queryByLabelText('Oberste Ebene')).not.toBeInTheDocument()

    drag(screen.getByRole('group', { name: 'Abteilung Innendienst' }), card('Lager'))
    await waitFor(() =>
      expect(last(calls, 'PATCH', '/departments/{department_id}')?.init).toMatchObject({
        params: { path: { department_id: 3 } },
        body: { parent_id: 4, clear_parent_id: false },
      }),
    )
  })

  it('zeigt Fehler beim Umhängen', async () => {
    loginAs({ kind: 'hr', role: 'HR' })
    mockApi(
      editRoutes({
        'PATCH /departments/{department_id}': new ApiFailure(400, 'SUPERVISOR_CYCLE', 'Damit wäre Bea Test (indirekt) die eigene Führungskraft.'),
      }),
    )
    renderWithProviders(<OrgChart />)
    drag(await screen.findByRole('group', { name: 'Abteilung Innendienst' }), card('Lager'))
    expect(await screen.findByRole('alert')).toHaveTextContent('die eigene Führungskraft')
  })
})

describe('Abteilungen', () => {
  it('zeigt verschachtelte Abteilungen mit Leitungen und Stellvertretungen und legt neue an', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const calls = mockApi({
      'GET /departments': [
        {
          id: 1, name: 'Vertrieb', parent_id: null, employee_count: 3,
          leaders: [leader(7, 'Tom Teamleiter', 'HEAD'), leader(8, 'Ina Vize', 'DEPUTY', 'ABSENCE')],
        },
        { id: 2, name: 'Innendienst', parent_id: 1, leaders: [leader(9, 'Alt Chef', 'HEAD', 'STANDBY', false)], employee_count: 1 },
        { id: 3, name: 'Lager', parent_id: null, leaders: [], employee_count: 0 },
      ],
      'GET /employees': [employee({ id: 7, first_name: 'Tom', last_name: 'Teamleiter' }), employee({ id: 8, first_name: 'Ina', last_name: 'Vize' })],
      'POST /departments': { id: 4, name: 'Werk', parent_id: null, leaders: [], employee_count: 0 },
    })
    renderWithProviders(<DepartmentsPage />)
    const rows = await screen.findAllByRole('row')
    expect(rows.map((row) => row.textContent)).toEqual(
      expect.arrayContaining([
        expect.stringContaining('VertriebTom TeamleiterStellv.: Ina Vize (nur bei Abwesenheit)3'),
        expect.stringContaining('└InnendienstAlt Chef (inaktiv)1'),
        expect.stringContaining('Lager–0'),
      ]),
    )
    await userEvent.click(screen.getByRole('button', { name: /Neue Abteilung/ }))
    await userEvent.type(screen.getByLabelText('Name'), 'Werk')
    await choose('Person hinzufügen', 'Teamleiter, Tom')
    await choose('Person hinzufügen', 'Vize, Ina')
    await choose('Rechte von Ina Vize', 'Gleiche Rechte wie die Leitung')
    expect(screen.getByText('Sieht und entscheidet immer und wird wie die Leitung benachrichtigt.')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Person hinzufügen' })).toBeDisabled() // alle schon eingetragen
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.init.body).toEqual({
        name: 'Werk',
        parent_id: null,
        leaders: [
          { employee_id: 7, role: 'HEAD', deputy_rights: 'STANDBY' },
          { employee_id: 8, role: 'DEPUTY', deputy_rights: 'FULL' },
        ],
      }),
    )
  })

  it('entfernt beim Bearbeiten alle Leitungen – auch inaktive – und zeigt Fehler', async () => {
    loginAs({ kind: 'hr', role: 'ADMIN' })
    const vertrieb = { id: 1, name: 'Vertrieb', parent_id: null, employee_count: 3, leaders: [leader(9, 'Alt Chef', 'HEAD', 'STANDBY', false)] }
    let fail = true
    const calls = mockApi({
      'GET /departments': [vertrieb],
      'GET /employees': [employee({ id: 7, first_name: 'Tom', last_name: 'Teamleiter' })],
      'PATCH /departments/{department_id}': () => {
        if (fail) {
          fail = false
          return new ApiFailure(409, 'DEPARTMENT_NAME_TAKEN', 'Diese Abteilung gibt es schon.')
        }
        return { ...vertrieb, leaders: [] }
      },
    })
    renderWithProviders(<DepartmentsPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    expect(within(await screen.findByRole('dialog')).getByText('Alt Chef (inaktiv)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Alt Chef (inaktiv) entfernen' }))
    expect(screen.getByText('Noch niemand eingetragen.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Diese Abteilung gibt es schon.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'PATCH').at(-1)?.init.body).toMatchObject({ leaders: [], clear_parent_id: true, parent_id: null }),
    )
  })
})
