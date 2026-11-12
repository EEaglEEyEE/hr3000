import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useCostCentersQuery } from '../api/queries/personalData'
import {
  useCreateCustomerMutation,
  useCreateProjectMutation,
  useCustomersQuery,
  useDeleteCustomerMutation,
  useDeleteProjectMutation,
  useProjectsQuery,
  useUpdateCustomerMutation,
  useUpdateProjectMutation,
  type Project,
} from '../api/queries/projects'
import { useUpdateSettingsMutation, type Settings } from '../api/queries/settings'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { formatDate } from '../lib/format'

function errorText(err: unknown): string {
  return err instanceof ApiError && err.code ? err.message : 'Das hat nicht geklappt – bitte Eingaben prüfen.'
}

/** Einstellungen → „Projekte & Kunden“: Schalter (nur Admin), Kunden und Projekte (Admin/HR). */
export function ProjectsPage({ settings }: { settings?: Settings }) {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-lg font-semibold text-slate-900">Projekte &amp; Kunden</h1>
      {settings && <ProjectSwitches settings={settings} />}
      <CustomersCard />
      <ProjectsCard />
    </div>
  )
}

function ProjectSwitches({ settings }: { settings: Settings }) {
  const update = useUpdateSettingsMutation()
  const enabled = settings.project_times_enabled ?? false
  return (
    <div className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4">
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={enabled}
          disabled={update.isPending}
          onChange={(e) => update.mutate({ project_times_enabled: e.target.checked })}
        />
        <span>
          <span className="font-medium text-slate-800">Projektzeiten</span>
          <span className="block text-slate-500">
            Mitarbeiter ordnen selbst eingetragene Zeiten (Stundenzettel) einem Projekt zu, optional mit Tätigkeit. Unter
            „Analysen“ gibt es die Auswertung „Projektzeiten“. Am Tablet und beim Stempeln gibt es keine Projektauswahl.
          </span>
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.project_required ?? false}
          disabled={update.isPending || !enabled}
          onChange={(e) => update.mutate({ project_required: e.target.checked })}
        />
        <span>
          Projekt ist Pflicht
          <span className="block text-xs text-slate-500">Jede selbst eingetragene Arbeitszeit braucht ein Projekt.</span>
        </span>
      </label>
      {update.isError && <p className="text-sm text-red-600">{errorText(update.error)}</p>}
    </div>
  )
}

function CustomersCard() {
  const query = useCustomersQuery()
  const create = useCreateCustomerMutation()
  const update = useUpdateCustomerMutation()
  const remove = useDeleteCustomerMutation()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const onError = (err: Error) => setError(errorText(err))

  function handleCreate(event: FormEvent) {
    event.preventDefault()
    setError(null)
    create.mutate(name, { onSuccess: () => setName(''), onError })
  }

  const customers = query.data ?? []
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-medium text-slate-800">Kunden</h2>
      <form className="flex flex-wrap items-end gap-2" onSubmit={handleCreate}>
        <div className="flex max-w-full flex-col gap-1.5">
          <Label htmlFor="customer-name">Name</Label>
          <Input id="customer-name" className="w-64 max-w-full" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Button type="submit" disabled={create.isPending}>
          Kunde hinzufügen
        </Button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {customers.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Projekte</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {customers.map((customer) => (
              <TableRow key={customer.id} className={customer.active ? undefined : 'text-slate-400'}>
                <TableCell>
                  {customer.name}
                  {!customer.active && ' (inaktiv)'}
                </TableCell>
                <TableCell>{customer.project_count}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => update.mutate({ id: customer.id, active: !customer.active }, { onError })}
                    >
                      {customer.active ? 'Deaktivieren' : 'Aktivieren'}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => remove.mutate(customer.id, { onError })}>
                      Löschen
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  )
}

interface ProjectDraft {
  name: string
  number: string
  customer_id: string
  cost_center_id: string
  billable: boolean
  valid_from: string
  valid_to: string
}

const EMPTY: ProjectDraft = { name: '', number: '', customer_id: '', cost_center_id: '', billable: true, valid_from: '', valid_to: '' }

function draftOf(project: Project): ProjectDraft {
  return {
    name: project.name,
    number: project.number ?? '',
    customer_id: project.customer_id != null ? String(project.customer_id) : '',
    cost_center_id: project.cost_center_id != null ? String(project.cost_center_id) : '',
    billable: project.billable,
    valid_from: project.valid_from ?? '',
    valid_to: project.valid_to ?? '',
  }
}

function payloadOf(draft: ProjectDraft) {
  return {
    name: draft.name.trim(),
    number: draft.number.trim() || null,
    customer_id: draft.customer_id ? Number(draft.customer_id) : null,
    cost_center_id: draft.cost_center_id ? Number(draft.cost_center_id) : null,
    billable: draft.billable,
    valid_from: draft.valid_from || null,
    valid_to: draft.valid_to || null,
  }
}

function ProjectsCard() {
  const query = useProjectsQuery()
  const customers = (useCustomersQuery().data ?? []).filter((c) => c.active)
  const costCenters = (useCostCentersQuery(false).data ?? [])
  const create = useCreateProjectMutation()
  const update = useUpdateProjectMutation()
  const remove = useDeleteProjectMutation()
  const [draft, setDraft] = useState<ProjectDraft>(EMPTY)
  const [editing, setEditing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const onError = (err: Error) => setError(errorText(err))

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    const done = { onSuccess: () => { setDraft(EMPTY); setEditing(null) }, onError }
    if (editing === null) create.mutate({ ...payloadOf(draft), active: true }, done)
    else update.mutate({ id: editing, body: payloadOf(draft) }, done)
  }

  const set = (patch: Partial<ProjectDraft>) => setDraft((current) => ({ ...current, ...patch }))
  const projects = query.data ?? []
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-medium text-slate-800">Projekte</h2>
      <p className="text-sm text-slate-500">
        Projekte, denen schon Zeiten zugeordnet sind, lassen sich nicht löschen – nur deaktivieren. Mit „Gültig von/bis“ ist
        ein Projekt nur in diesem Zeitraum auswählbar.
      </p>
      <form className="grid grid-cols-[repeat(auto-fill,minmax(12rem,1fr))] gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleSubmit}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="project-name">Name</Label>
          <Input id="project-name" required maxLength={120} value={draft.name} onChange={(e) => set({ name: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="project-number">Nummer (optional)</Label>
          <Input id="project-number" maxLength={40} value={draft.number} onChange={(e) => set({ number: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="project-customer">Kunde (optional)</Label>
          <select
            id="project-customer"
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={draft.customer_id}
            onChange={(e) => set({ customer_id: e.target.value })}
          >
            <option value="">Kein Kunde</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="project-cost-center">Kostenstelle (optional)</Label>
          <select
            id="project-cost-center"
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={draft.cost_center_id}
            onChange={(e) => set({ cost_center_id: e.target.value })}
          >
            <option value="">Keine Kostenstelle</option>
            {costCenters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="project-from">Gültig von</Label>
          <Input id="project-from" type="date" value={draft.valid_from} onChange={(e) => set({ valid_from: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="project-to">Gültig bis</Label>
          <Input id="project-to" type="date" value={draft.valid_to} onChange={(e) => set({ valid_to: e.target.value })} />
        </div>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" checked={draft.billable} onChange={(e) => set({ billable: e.target.checked })} />
          Abrechenbar
        </label>
        <div className="flex items-end gap-2">
          <Button type="submit" disabled={create.isPending || update.isPending}>
            {editing === null ? 'Projekt hinzufügen' : 'Speichern'}
          </Button>
          {editing !== null && (
            <Button type="button" variant="outline" onClick={() => { setEditing(null); setDraft(EMPTY) }}>
              Abbrechen
            </Button>
          )}
        </div>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {projects.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Projekt</TableHead>
              <TableHead>Kunde</TableHead>
              <TableHead>Kostenstelle</TableHead>
              <TableHead>Gültig</TableHead>
              <TableHead>Abrechenbar</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {projects.map((project) => (
              <TableRow key={project.id} className={project.active ? undefined : 'text-slate-400'}>
                <TableCell>
                  {project.number && <span className="font-mono">{project.number} </span>}
                  {project.name}
                  {!project.active && ' (inaktiv)'}
                </TableCell>
                <TableCell>{project.customer_name ?? '–'}</TableCell>
                <TableCell>{project.cost_center_label ?? '–'}</TableCell>
                <TableCell className="whitespace-nowrap text-sm">
                  {project.valid_from || project.valid_to
                    ? `${project.valid_from ? formatDate(project.valid_from) : '…'} – ${project.valid_to ? formatDate(project.valid_to) : '…'}`
                    : 'immer'}
                </TableCell>
                <TableCell>{project.billable ? <Badge variant="success">Ja</Badge> : <Badge>Nein</Badge>}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setEditing(project.id)
                        setDraft(draftOf(project))
                        setError(null)
                      }}
                    >
                      Bearbeiten
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => update.mutate({ id: project.id, body: { active: !project.active } }, { onError })}
                    >
                      {project.active ? 'Deaktivieren' : 'Aktivieren'}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={project.in_use}
                      title={project.in_use ? 'Dem Projekt sind schon Zeiten zugeordnet' : undefined}
                      onClick={() => remove.mutate(project.id, { onError })}
                    >
                      Löschen
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  )
}
