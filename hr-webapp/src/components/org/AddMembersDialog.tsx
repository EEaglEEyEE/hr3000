import { useMemo, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import {
  useAddDepartmentMembersMutation,
  type OrgChartDepartment,
  type OrgChartPerson,
} from '../../api/queries/departments'
import { departmentPaths } from '../../lib/departments'
import { personMatches } from '../../lib/orgTree'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'

const fullName = (person: OrgChartPerson) => `${person.first_name} ${person.last_name}`

interface Group {
  key: 'none' | 'other'
  title: string
  people: OrgChartPerson[]
}

/** Mitarbeiter in eine Abteilung aufnehmen: mehrere auf einmal, mit Suche – zuerst wer noch keine
 *  Abteilung hat, dann wer aus einer anderen Abteilung hierher wechseln soll. */
export function AddMembersDialog({
  department,
  people,
  departments,
  onClose,
}: {
  department: OrgChartDepartment | null
  /** Aktive Mitarbeiter (wie im Organigramm) */
  people: OrgChartPerson[]
  departments: OrgChartDepartment[]
  onClose: () => void
}) {
  const addMembers = useAddDepartmentMembersMutation()
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [shownFor, setShownFor] = useState<number | null>(null)
  if (department && shownFor !== department.id) {
    setShownFor(department.id)
    setSelected(new Set())
    setSearch('')
    setError(null)
  }

  const paths = useMemo(() => departmentPaths(departments), [departments])
  const roles = new Map((department?.leaders ?? []).map((l) => [l.employee_id, l.role]))
  const term = search.trim().toLowerCase()
  const matches = (person: OrgChartPerson) =>
    term === '' ||
    personMatches(person, term) ||
    (person.department_id !== null && (paths.get(person.department_id) ?? '').toLowerCase().includes(term))
  const candidates = department ? people.filter((p) => p.department_id !== department.id) : []
  const groups: Group[] = [
    { key: 'none' as const, title: 'Ohne Abteilung', people: candidates.filter((p) => p.department_id === null && matches(p)) },
    {
      key: 'other' as const,
      title: 'Aus anderen Abteilungen (wechseln hierher)',
      people: candidates.filter((p) => p.department_id !== null && matches(p)),
    },
  ].filter((group) => group.people.length > 0)

  function toggle(id: number) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }

  function toggleGroup(group: Group) {
    const all = group.people.every((p) => selected.has(p.employee_id))
    const next = new Set(selected)
    for (const person of group.people) {
      if (all) next.delete(person.employee_id)
      else next.add(person.employee_id)
    }
    setSelected(next)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!department || selected.size === 0) return
    setError(null)
    // Reihenfolge wie in der Liste, nicht wie angeklickt
    const ids = candidates.filter((p) => selected.has(p.employee_id)).map((p) => p.employee_id)
    addMembers.mutate(
      { id: department.id, employeeIds: ids },
      {
        onSuccess: onClose,
        onError: (err) => setError(err instanceof ApiError ? err.message : 'Hinzufügen fehlgeschlagen.'),
      },
    )
  }

  const count = selected.size
  return (
    <Dialog open={department !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{department ? `Mitarbeiter zu ${department.name} hinzufügen` : 'Mitarbeiter hinzufügen'}</DialogTitle>
          <p className="text-sm text-slate-500">
            Führungskraft wird die Leitung dieser Abteilung, außer bei einer je Person eingetragenen Führungskraft.
          </p>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          {candidates.length === 0 ? (
            <p className="text-sm text-slate-500">Alle aktiven Mitarbeiter sind schon in dieser Abteilung.</p>
          ) : (
            <>
              <Input
                placeholder="Name, Position oder Abteilung suchen"
                aria-label="Mitarbeiter suchen"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <div className="flex max-h-[min(24rem,50dvh)] flex-col gap-3 overflow-y-auto rounded-md border border-slate-200 p-2">
                {groups.length === 0 && <p className="px-1 py-2 text-sm text-slate-500">Niemand gefunden.</p>}
                {groups.map((group) => {
                  const all = group.people.every((p) => selected.has(p.employee_id))
                  return (
                    <section key={group.key} aria-label={group.title} className="flex flex-col gap-1">
                      <div className="flex items-center justify-between gap-2 px-1">
                        <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">
                          {group.title} ({group.people.length})
                        </h3>
                        <button
                          type="button"
                          className="shrink-0 text-xs text-sky-700 hover:underline"
                          onClick={() => toggleGroup(group)}
                        >
                          {all ? 'Keine' : 'Alle'} auswählen
                        </button>
                      </div>
                      <ul className="flex flex-col">
                        {group.people.map((person) => {
                          const role = roles.get(person.employee_id)
                          const hints = [
                            person.position,
                            person.department_id !== null ? `bisher ${paths.get(person.department_id) ?? person.department ?? ''}` : null,
                            role === 'HEAD' ? 'leitet diese Abteilung' : role === 'DEPUTY' ? 'Stellvertretung hier' : null,
                          ].filter(Boolean)
                          return (
                            <li key={person.employee_id}>
                              <label className="flex cursor-pointer items-start gap-2 rounded px-1 py-2 hover:bg-slate-50 sm:py-1.5">
                                <input
                                  type="checkbox"
                                  className="mt-0.5 h-4 w-4 shrink-0"
                                  checked={selected.has(person.employee_id)}
                                  onChange={() => toggle(person.employee_id)}
                                />
                                <span className="min-w-0 flex-1">
                                  <span className="block text-sm text-slate-900">{fullName(person)}</span>
                                  {hints.length > 0 && <span className="block text-xs text-slate-500">{hints.join(' · ')}</span>}
                                </span>
                              </label>
                            </li>
                          )
                        })}
                      </ul>
                    </section>
                  )
                })}
              </div>
            </>
          )}
          {error && (
            <p className="text-sm text-red-600" role="alert">
              {error}
            </p>
          )}
          <DialogFooter className="mt-3">
            <Button type="button" variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={count === 0 || addMembers.isPending}>
              {count === 0 ? 'Hinzufügen' : `${count} hinzufügen`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
