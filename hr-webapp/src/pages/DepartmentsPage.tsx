import { useState } from 'react'
import { Plus } from 'lucide-react'
import { ApiError } from '../api/client'
import { departmentTree, useDeleteDepartmentMutation, useDepartmentsQuery, type Department } from '../api/queries/departments'
import { DepartmentDialog } from '../components/org/DepartmentDialog'
import { Button } from '../components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { DEPUTY_RIGHTS_SHORT } from '../lib/leaders'

/** Leitungen und Stellvertretungen einer Abteilung, kurz (für Tabelle). */
function LeadersCell({ department }: { department: Department }) {
  const heads = department.leaders.filter((l) => l.role === 'HEAD')
  const deputies = department.leaders.filter((l) => l.role === 'DEPUTY')
  if (heads.length === 0 && deputies.length === 0) return <span className="text-slate-400">–</span>
  const name = (l: Department['leaders'][number]) => (l.active ? l.name : `${l.name} (inaktiv)`)
  return (
    <div className="flex flex-col gap-0.5">
      {heads.length > 0 && <span>{heads.map(name).join(', ')}</span>}
      {deputies.length > 0 && (
        <span className="text-xs text-slate-500">
          Stellv.: {deputies.map((d) => `${name(d)} (${DEPUTY_RIGHTS_SHORT[d.deputy_rights]})`).join(', ')}
        </span>
      )}
    </div>
  )
}

/** Abteilungen (hierarchisch) mit Leitungen und Stellvertretungen – die einzige Organisationsstruktur:
 *  Grundlage für „Abteilung“ am Mitarbeiter, die Führungskräfte (= Leitungen) und das Organigramm. */
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
        Abteilungen lassen sich verschachteln (z. B. Vertrieb → Innendienst). Die Leitungen sind die Führungskräfte aller
        Mitarbeiter der Abteilung – auch in Unterabteilungen ohne eigene Leitung. Stellvertretungen springen je nach ihren
        Rechten ein. Mit Login und Rolle „Führungskraft“ sehen sie das Tagesgeschäft und genehmigen Anträge. Am
        Mitarbeiter lässt sich eine abweichende Führungskraft eintragen. Alles lässt sich auch direkt im Organigramm
        bearbeiten.
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {departmentsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {departmentsQuery.data && tree.length === 0 && <p className="text-sm text-slate-500">Noch keine Abteilungen.</p>}
      {tree.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Leitung und Stellvertretung</TableHead>
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
                <TableCell>
                  <LeadersCell department={department} />
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
