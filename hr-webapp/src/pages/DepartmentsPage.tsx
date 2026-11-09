import { useEffect, useState, type FormEvent } from 'react'
import { Plus } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  departmentTree,
  useCreateDepartmentMutation,
  useDeleteDepartmentMutation,
  useDepartmentsQuery,
  useUpdateDepartmentMutation,
  type Department,
} from '../api/queries/departments'
import { Button } from '../components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

const NONE = 'none'

/** Abteilungen (hierarchisch) – Grundlage für „Abteilung“ am Mitarbeiter und das Organigramm. */
export function DepartmentsPage() {
  const departmentsQuery = useDepartmentsQuery()
  const remove = useDeleteDepartmentMutation()
  const [editing, setEditing] = useState<Department | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const tree = departmentTree(departmentsQuery.data ?? [])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Abteilungen</h1>
        <Button onClick={() => setEditing(null)}>
          <Plus className="h-4 w-4" />
          Neue Abteilung
        </Button>
      </div>
      <p className="text-sm text-slate-500">
        Abteilungen lassen sich verschachteln (z. B. Vertrieb → Innendienst). Am Mitarbeiter wählst du Abteilung,
        Position und Führungskraft; daraus entsteht das Organigramm.
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {departmentsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {departmentsQuery.data && tree.length === 0 && <p className="text-sm text-slate-500">Noch keine Abteilungen.</p>}
      {tree.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Mitarbeiter</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {tree.map(({ department, depth }) => (
              <TableRow key={department.id}>
                <TableCell>
                  <span style={{ paddingLeft: `${depth * 1.25}rem` }}>
                    {depth > 0 && <span className="mr-1 text-slate-400">└</span>}
                    {department.name}
                  </span>
                </TableCell>
                <TableCell className="text-slate-500">{department.employee_count}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setEditing(department)}>
                      Bearbeiten
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={remove.isPending}
                      onClick={() => {
                        setError(null)
                        remove.mutate(department.id, {
                          onError: (err) => setError(err instanceof ApiError ? err.message : 'Löschen fehlgeschlagen.'),
                        })
                      }}
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
      <DepartmentDialog
        department={editing}
        departments={departmentsQuery.data ?? []}
        onClose={() => setEditing(undefined)}
      />
    </div>
  )
}

/** undefined = geschlossen, null = neue Abteilung */
function DepartmentDialog({
  department,
  departments,
  onClose,
}: {
  department: Department | null | undefined
  departments: Department[]
  onClose: () => void
}) {
  const create = useCreateDepartmentMutation()
  const update = useUpdateDepartmentMutation()
  const [name, setName] = useState('')
  const [parent, setParent] = useState(NONE)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (department === undefined) return
    setName(department?.name ?? '')
    setParent(department?.parent_id ? String(department.parent_id) : NONE)
    setError(null)
  }, [department])

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const onError = (err: Error) => setError(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen.')
    const parentId = parent === NONE ? null : Number(parent)
    if (department) {
      update.mutate(
        { id: department.id, payload: { name, parent_id: parentId, clear_parent_id: parentId === null } },
        { onSuccess: onClose, onError },
      )
    } else {
      create.mutate({ name, parent_id: parentId }, { onSuccess: onClose, onError })
    }
  }

  const choices = departmentTree(departments).filter(({ department: d }) => d.id !== department?.id)
  return (
    <Dialog open={department !== undefined} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
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
                    {' '.repeat(depth * 3)}
                    {d.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
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
