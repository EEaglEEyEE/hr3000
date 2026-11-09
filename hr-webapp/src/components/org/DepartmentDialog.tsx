import { useEffect, useState, type FormEvent } from 'react'
import { X } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  departmentTree,
  useCreateDepartmentMutation,
  useUpdateDepartmentMutation,
  type Department,
  type DepartmentLeaderInput,
} from '../../api/queries/departments'
import { useEmployeesQuery } from '../../api/queries/employees'
import { DEPUTY_RIGHTS_HELP, DEPUTY_RIGHTS_LABELS, ROLE_LABELS, type DeputyRights, type LeaderRole } from '../../lib/leaders'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

const NONE = 'none'

type Row = { employee_id: number; role: LeaderRole; deputy_rights: DeputyRights }

/** Abteilung anlegen oder bearbeiten: Name, übergeordnete Abteilung, Leitungen und Stellvertretungen.
 *  department: undefined = geschlossen, null = neue Abteilung (optional unter parentId). */
export function DepartmentDialog({
  department,
  parentId = null,
  departments,
  onClose,
}: {
  department: Department | null | undefined
  parentId?: number | null
  departments: Department[]
  onClose: () => void
}) {
  const create = useCreateDepartmentMutation()
  const update = useUpdateDepartmentMutation()
  const employeesQuery = useEmployeesQuery({ active: true })
  const [name, setName] = useState('')
  const [parent, setParent] = useState(NONE)
  const [rows, setRows] = useState<Row[]>([])
  const [addKey, setAddKey] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (department === undefined) return
    setName(department?.name ?? '')
    const presetParent = department ? department.parent_id : parentId
    setParent(presetParent ? String(presetParent) : NONE)
    setRows(
      (department?.leaders ?? []).map((l) => ({ employee_id: l.employee_id, role: l.role, deputy_rights: l.deputy_rights })),
    )
    setError(null)
  }, [department, parentId])

  const people = employeesQuery.data ?? []
  const names = new Map<number, string>()
  for (const leader of department?.leaders ?? []) {
    names.set(leader.employee_id, leader.active ? leader.name : `${leader.name} (inaktiv)`)
  }
  for (const person of people) names.set(person.id, `${person.first_name} ${person.last_name}`)
  const nameOf = (id: number) => names.get(id) ?? `#${id}`
  const addable = people
    .filter((p) => !rows.some((r) => r.employee_id === p.id))
    .sort((a, b) => a.last_name.localeCompare(b.last_name, 'de') || a.first_name.localeCompare(b.first_name, 'de'))

  function change(index: number, patch: Partial<Row>) {
    setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  function add(value: string) {
    const role: LeaderRole = rows.some((r) => r.role === 'HEAD') ? 'DEPUTY' : 'HEAD'
    setRows([...rows, { employee_id: Number(value), role, deputy_rights: 'STANDBY' }])
    setAddKey(addKey + 1)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const onError = (err: Error) => setError(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen.')
    const parentValue = parent === NONE ? null : Number(parent)
    const leaders: DepartmentLeaderInput[] = rows.map((r) => ({
      employee_id: r.employee_id,
      role: r.role,
      deputy_rights: r.deputy_rights,
    }))
    if (department) {
      update.mutate(
        {
          id: department.id,
          payload: { name, parent_id: parentValue, clear_parent_id: parentValue === null, leaders },
        },
        { onSuccess: onClose, onError },
      )
    } else {
      create.mutate({ name, parent_id: parentValue, leaders }, { onSuccess: onClose, onError })
    }
  }

  const choices = departmentTree(departments).filter(({ department: d }) => d.id !== department?.id)
  return (
    <Dialog open={department !== undefined} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{department ? 'Abteilung bearbeiten' : 'Neue Abteilung'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="department-name">Name</Label>
            <Input id="department-name" required maxLength={150} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="department-parent">Übergeordnete Abteilung</Label>
            <Select value={parent} onValueChange={setParent}>
              <SelectTrigger id="department-parent">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>– keine (oberste Ebene) –</SelectItem>
                {choices.map(({ department: d, depth }) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {' '.repeat(depth * 3)}
                    {d.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1.5 text-sm font-medium text-slate-900">Leitung und Stellvertretung</legend>
            {rows.length === 0 && <p className="text-sm text-slate-500">Noch niemand eingetragen.</p>}
            <ul className="flex flex-col gap-2">
              {rows.map((row, index) => {
                const label = nameOf(row.employee_id)
                return (
                  <li key={row.employee_id} className="flex flex-col gap-1.5 rounded-md border border-slate-200 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-sm text-slate-900">{label}</span>
                      <button
                        type="button"
                        className="shrink-0 rounded p-1 text-slate-400 hover:text-slate-700"
                        aria-label={`${label} entfernen`}
                        onClick={() => setRows(rows.filter((_, i) => i !== index))}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Select value={row.role} onValueChange={(value) => change(index, { role: value as LeaderRole })}>
                        <SelectTrigger className="w-40" aria-label={`Rolle von ${label}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(['HEAD', 'DEPUTY'] as const).map((role) => (
                            <SelectItem key={role} value={role}>
                              {ROLE_LABELS[role]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {row.role === 'DEPUTY' && (
                        <Select
                          value={row.deputy_rights}
                          onValueChange={(value) => change(index, { deputy_rights: value as DeputyRights })}
                        >
                          <SelectTrigger className="min-w-0 flex-1" aria-label={`Rechte von ${label}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {(['STANDBY', 'FULL', 'ABSENCE'] as const).map((rights) => (
                              <SelectItem key={rights} value={rights}>
                                {DEPUTY_RIGHTS_LABELS[rights]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    </div>
                    {row.role === 'DEPUTY' && <p className="text-xs text-slate-500">{DEPUTY_RIGHTS_HELP[row.deputy_rights]}</p>}
                  </li>
                )
              })}
            </ul>
            <Select key={addKey} onValueChange={add} disabled={addable.length === 0}>
              <SelectTrigger aria-label="Person hinzufügen">
                <SelectValue placeholder="Person hinzufügen…" />
              </SelectTrigger>
              <SelectContent>
                {addable.map((person) => (
                  <SelectItem key={person.id} value={String(person.id)}>
                    {person.last_name}, {person.first_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-slate-500">
              Leitungen sind gleichberechtigt die Führungskräfte aller in dieser Abteilung (ohne Leitung gilt die der
              übergeordneten). Eine Leitung selbst berichtet an die Leitung darüber. Mit Login und Rolle „Führungskraft“
              sehen sie das Tagesgeschäft und genehmigen Anträge.
            </p>
          </fieldset>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={create.isPending || update.isPending}>
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
