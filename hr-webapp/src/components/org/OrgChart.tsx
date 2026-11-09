import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
  type ReactNode,
} from 'react'
import { ArrowRightLeft, ChevronDown, ChevronRight, ChevronUp, Pencil, Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  useDeleteDepartmentMutation,
  useDepartmentsQuery,
  useOrgChartQuery,
  useUpdateDepartmentMutation,
  type OrgChartDepartment,
  type OrgChartPerson,
} from '../../api/queries/departments'
import { useUpdateEmployeeMutation } from '../../api/queries/employees'
import { useAuth } from '../../auth/AuthContext'
import { departmentPaths } from '../../lib/departments'
import { DEPUTY_RIGHTS_SHORT } from '../../lib/leaders'
import { buildOrgTree, personMatches, subtreeIds, type OrgNode as GenericOrgNode } from '../../lib/orgTree'
import { cn } from '../../lib/utils'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { DepartmentDialog } from './DepartmentDialog'

type OrgNode = GenericOrgNode<OrgChartPerson>

const fullName = (person: OrgChartPerson) => `${person.first_name} ${person.last_name}`

function nodeMatches(node: OrgNode, query: string): boolean {
  return (
    node.department.name.toLowerCase().includes(query) ||
    node.heads.some((h) => personMatches(h, query)) ||
    node.deputies.some((d) => personMatches(d.person, query)) ||
    node.members.some((m) => personMatches(m, query))
  )
}

function containsMatch(node: OrgNode, query: string): boolean {
  return nodeMatches(node, query) || node.children.some((child) => containsMatch(child, query))
}

// --- Bearbeiten (Admin/HR): Dialoge, Verschieben, Ziehen und Ablegen am Desktop ------------------

type DragItem = { kind: 'person'; id: number } | { kind: 'department'; id: number }
/** Eigener Datentyp, damit nichts anderes (Text, Dateien) als Organigramm-Eintrag abgelegt wird */
const DRAG_TYPE = 'application/x-hr3000-org'

interface OrgEditing {
  canEdit: boolean
  dragging: DragItem | null
  startDrag: (item: DragItem, event: DragEvent) => void
  endDrag: () => void
  /** target = Abteilung oder null (Person: ohne Abteilung, Abteilung: oberste Ebene) */
  canDrop: (target: number | null) => boolean
  drop: (target: number | null) => void
  edit: (department: OrgChartDepartment) => void
  addChild: (department: OrgChartDepartment) => void
  remove: (department: OrgChartDepartment) => void
  move: (person: OrgChartPerson) => void
}

const READ_ONLY: OrgEditing = {
  canEdit: false,
  dragging: null,
  startDrag: () => {},
  endDrag: () => {},
  canDrop: () => false,
  drop: () => {},
  edit: () => {},
  addChild: () => {},
  remove: () => {},
  move: () => {},
}

const EditingContext = createContext<OrgEditing>(READ_ONLY)

/** Ablageziel: hebt sich beim Darüberziehen hervor, nimmt nur passende Einträge an. */
function useDropTarget(target: number | null) {
  const editing = useContext(EditingContext)
  const [over, setOver] = useState(false)
  const enabled = editing.dragging !== null && editing.canDrop(target)
  return {
    enabled,
    over: enabled && over,
    props: enabled
      ? {
          onDragOver: (event: DragEvent) => {
            event.preventDefault()
            if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
            setOver(true)
          },
          onDragLeave: () => setOver(false),
          onDrop: (event: DragEvent) => {
            event.preventDefault()
            event.stopPropagation()
            setOver(false)
            editing.drop(target)
          },
        }
      : {},
  }
}

function dragProps(editing: OrgEditing, item: DragItem) {
  if (!editing.canEdit) return {}
  return {
    draggable: true,
    onDragStart: (event: DragEvent) => {
      event.stopPropagation() // Person in einer Karte: nicht zugleich die Karte ziehen
      editing.startDrag(item, event)
    },
    onDragEnd: () => editing.endDrag(),
  }
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-900 sm:p-1"
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

// --- Darstellung --------------------------------------------------------------------------------

function SizeBadge({ size }: { size: number }) {
  if (size === 0) return null
  return (
    <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600" title="Personen in der Abteilung und darunter">
      {size}
    </span>
  )
}

function PersonLine({ person, query }: { person: OrgChartPerson; query: string }) {
  const editing = useContext(EditingContext)
  const hit = query !== '' && personMatches(person, query)
  return (
    <li
      className={cn('flex items-center gap-1', hit && 'font-medium text-sky-700', editing.canEdit && 'cursor-grab')}
      title={[fullName(person), person.position].filter(Boolean).join(' · ')}
      {...dragProps(editing, { kind: 'person', id: person.employee_id })}
    >
      <span className="min-w-0 flex-1 truncate">
        {fullName(person)}
        {person.position && <span className="text-slate-400"> · {person.position}</span>}
      </span>
      {editing.canEdit && (
        <IconButton label={`${fullName(person)} verschieben`} onClick={() => editing.move(person)}>
          <ArrowRightLeft className="h-3.5 w-3.5" />
        </IconButton>
      )}
    </li>
  )
}

function Names({ people, query }: { people: OrgChartPerson[]; query: string }) {
  return (
    <>
      {people.map((person, index) => (
        <span key={person.employee_id}>
          {index > 0 && ', '}
          <span className={cn(query !== '' && personMatches(person, query) && 'font-medium text-sky-700')}>{fullName(person)}</span>
        </span>
      ))}
    </>
  )
}

/** Abteilungskarte: Name, Leitungen, Stellvertretungen, aufklappbare Mitarbeiterliste. */
function DepartmentCard({ node, query, className }: { node: OrgNode; query: string; className?: string }) {
  const editing = useContext(EditingContext)
  const drop = useDropTarget(node.department.id)
  const searchHit = query !== '' && node.members.some((m) => personMatches(m, query))
  const [membersOpen, setMembersOpen] = useState(node.members.length <= 4)
  const showMembers = searchHit || membersOpen
  const hit = query !== '' && nodeMatches(node, query)
  const { name } = node.department
  return (
    <div
      className={cn(
        'flex flex-col gap-1 rounded-md border bg-white px-3 py-2 text-left shadow-sm',
        hit ? 'border-sky-500 ring-1 ring-sky-200' : 'border-slate-200',
        drop.enabled && 'border-dashed border-sky-400',
        drop.over && 'bg-sky-50 ring-2 ring-sky-400',
        className,
      )}
      data-drop-target={drop.enabled ? 'true' : undefined}
      role="group"
      aria-label={`Abteilung ${name}`}
      {...dragProps(editing, { kind: 'department', id: node.department.id })}
      {...drop.props}
    >
      <div className="flex items-start justify-between gap-2">
        <p className={cn('min-w-0 truncate text-sm font-semibold text-slate-900', editing.canEdit && 'cursor-grab')} title={name}>
          {name}
        </p>
        <div className="flex shrink-0 items-center gap-0.5">
          <SizeBadge size={node.size} />
          {editing.canEdit && (
            <>
              <IconButton label={`${name} bearbeiten`} onClick={() => editing.edit(node.department)}>
                <Pencil className="h-3.5 w-3.5" />
              </IconButton>
              <IconButton label={`Unterabteilung zu ${name} anlegen`} onClick={() => editing.addChild(node.department)}>
                <Plus className="h-3.5 w-3.5" />
              </IconButton>
              <IconButton label={`${name} löschen`} onClick={() => editing.remove(node.department)}>
                <Trash2 className="h-3.5 w-3.5" />
              </IconButton>
            </>
          )}
        </div>
      </div>
      <p className={cn('text-xs', node.heads.length > 0 ? 'text-slate-700' : 'text-slate-400')}>
        {node.heads.length > 0 ? (
          <>
            {node.heads.length === 1 ? 'Leitung' : 'Leitungen'}: <Names people={node.heads} query={query} />
          </>
        ) : (
          'ohne Leitung'
        )}
      </p>
      {node.deputies.length > 0 && (
        <p className="text-xs text-slate-600">
          Stellvertretung:{' '}
          {node.deputies.map(({ person, rights }, index) => (
            <span key={person.employee_id}>
              {index > 0 && ', '}
              <span className={cn(query !== '' && personMatches(person, query) && 'font-medium text-sky-700')}>{fullName(person)}</span>
              <span className="text-slate-400"> ({DEPUTY_RIGHTS_SHORT[rights]})</span>
            </span>
          ))}
        </p>
      )}
      {node.members.length > 0 && (
        <>
          <button
            type="button"
            className="flex items-center gap-1 self-start text-xs text-slate-500 hover:text-slate-900"
            onClick={() => setMembersOpen(!showMembers)}
            aria-expanded={showMembers}
          >
            {showMembers ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            {node.members.length} Mitarbeiter
          </button>
          {showMembers && (
            <ul className="flex flex-col gap-0.5 text-xs text-slate-600">
              {node.members.map((member) => (
                <PersonLine key={member.employee_id} person={member} query={query} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

const toggleLabel = (node: OrgNode, expanded: boolean) =>
  `Unterabteilungen von ${node.department.name} ${expanded ? 'zuklappen' : 'aufklappen'}`

// --- Baum (von oben nach unten, Linien per CSS: .org-tree in index.css) ---------------------------

function TreeNode({ node, depth, query }: { node: OrgNode; depth: number; query: string }) {
  const [open, setOpen] = useState(depth < 2)
  const visibleChildren = query ? node.children.filter((child) => containsMatch(child, query)) : node.children
  const expanded = query ? visibleChildren.length > 0 : open
  return (
    <li className="org-node">
      <div className="flex flex-col items-center">
        <DepartmentCard node={node} query={query} className="w-56" />
        {node.children.length > 0 && (
          <button
            type="button"
            className="mt-1 rounded text-slate-500 hover:text-slate-900"
            onClick={() => setOpen(!open)}
            aria-label={toggleLabel(node, expanded)}
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        )}
      </div>
      {expanded && visibleChildren.length > 0 && (
        <ul className="org-branch">
          {visibleChildren.map((child) => (
            <TreeNode key={child.department.id} node={child} depth={depth + 1} query={query} />
          ))}
        </ul>
      )}
    </li>
  )
}

/** Ein Baum in seinem Kasten: ist er breiter, scrollt er dort (nie die Seite) – anfangs mittig. */
function TreeBox({ node, query }: { node: OrgNode; query: string }) {
  const box = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const element = box.current
    if (element && element.scrollWidth > element.clientWidth) {
      element.scrollLeft = (element.scrollWidth - element.clientWidth) / 2
    }
  }, [])
  return (
    <div ref={box} className="org-tree overflow-x-auto pb-2" role="group" aria-label={`Baum ${node.department.name}`}>
      <ul className="org-branch">
        <TreeNode node={node} depth={0} query={query} />
      </ul>
    </div>
  )
}

// --- Liste (eingerückt, gut am Handy) ------------------------------------------------------------

function ListNode({ node, depth, query }: { node: OrgNode; depth: number; query: string }) {
  const [open, setOpen] = useState(depth < 2)
  const visibleChildren = query ? node.children.filter((child) => containsMatch(child, query)) : node.children
  const expanded = query ? visibleChildren.length > 0 : open
  return (
    <li className="flex flex-col gap-2">
      <div className="flex items-start gap-2">
        {node.children.length > 0 ? (
          <button
            type="button"
            className="mt-2.5 text-slate-500 hover:text-slate-900"
            onClick={() => setOpen(!open)}
            aria-label={toggleLabel(node, expanded)}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <DepartmentCard node={node} query={query} className="min-w-0 flex-1" />
      </div>
      {expanded && visibleChildren.length > 0 && (
        <ul className="ml-3 flex flex-col gap-2 border-l border-slate-200 pl-3">
          {visibleChildren.map((child) => (
            <ListNode key={child.department.id} node={child} depth={depth + 1} query={query} />
          ))}
        </ul>
      )}
    </li>
  )
}

function Unassigned({ people, query }: { people: OrgChartPerson[]; query: string }) {
  const editing = useContext(EditingContext)
  const drop = useDropTarget(null)
  const personDrag = editing.dragging?.kind === 'person'
  const shown = query ? people.filter((p) => personMatches(p, query)) : people
  if (shown.length === 0 && !(personDrag && drop.enabled)) return null
  return (
    <section
      className={cn('flex flex-col gap-2 rounded-md', personDrag && drop.enabled && 'border border-dashed border-sky-400 p-2', drop.over && 'bg-sky-50')}
      aria-label="Ohne Abteilung"
      {...(personDrag ? drop.props : {})}
    >
      <h3 className="text-sm font-medium text-slate-700">Ohne Abteilung ({shown.length})</h3>
      {shown.length === 0 && <p className="text-xs text-slate-500">Hierher ziehen: Person aus der Abteilung nehmen.</p>}
      <ul className="flex flex-wrap gap-2 text-sm">
        {shown.map((person) => (
          <li
            key={person.employee_id}
            className={cn(
              'flex items-center gap-1 rounded-md border bg-white px-3 py-1.5',
              query !== '' && personMatches(person, query) ? 'border-sky-500' : 'border-slate-200',
              editing.canEdit && 'cursor-grab',
            )}
            {...dragProps(editing, { kind: 'person', id: person.employee_id })}
          >
            <span className="text-slate-900">{fullName(person)}</span>
            {person.position && <span className="text-xs text-slate-500"> · {person.position}</span>}
            {editing.canEdit && (
              <IconButton label={`${fullName(person)} verschieben`} onClick={() => editing.move(person)}>
                <ArrowRightLeft className="h-3.5 w-3.5" />
              </IconButton>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Beim Ziehen einer Unterabteilung: hier ablegen = oberste Ebene. */
function TopLevelDrop() {
  const editing = useContext(EditingContext)
  const drop = useDropTarget(null)
  if (editing.dragging?.kind !== 'department' || !drop.enabled) return null
  return (
    <div
      className={cn('rounded-md border border-dashed border-sky-400 px-3 py-2 text-sm text-sky-700', drop.over && 'bg-sky-50')}
      aria-label="Oberste Ebene"
      {...drop.props}
    >
      Hierher ziehen: Abteilung auf die oberste Ebene
    </div>
  )
}

const NO_DEPARTMENT = 'none'

/** Person in eine andere Abteilung (oder ohne Abteilung) – die Alternative zum Ziehen, auch am Handy. */
function MovePersonDialog({
  person,
  departments,
  onClose,
  onMove,
  pending,
  error,
}: {
  person: OrgChartPerson | null
  departments: OrgChartDepartment[]
  onClose: () => void
  onMove: (person: OrgChartPerson, departmentId: number | null) => void
  pending: boolean
  error: string | null
}) {
  const [target, setTarget] = useState(NO_DEPARTMENT)
  const [shownFor, setShownFor] = useState<number | null>(null)
  if (person && shownFor !== person.employee_id) {
    setShownFor(person.employee_id)
    setTarget(person.department_id ? String(person.department_id) : NO_DEPARTMENT)
  }
  const paths = departmentPaths(departments)
  const options = [...departments].sort((a, b) => (paths.get(a.id) ?? '').localeCompare(paths.get(b.id) ?? '', 'de'))

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (person) onMove(person, target === NO_DEPARTMENT ? null : Number(target))
  }

  return (
    <Dialog open={person !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{person ? `${fullName(person)} verschieben` : 'Verschieben'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="move-department">Abteilung</Label>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger id="move-department">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_DEPARTMENT}>– ohne Abteilung –</SelectItem>
                {options.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {paths.get(d.id) ?? d.name}
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
            <Button type="submit" disabled={pending}>
              Verschieben
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

type View = 'tree' | 'list'
const VIEW_KEY = 'hr3000.orgchart.view'

/** Gespeicherte Wahl; ohne Wahl am Handy die Liste (ein breiter Baum müsste dort seitlich scrollen). */
function storedView(): View {
  try {
    const stored = localStorage.getItem(VIEW_KEY)
    if (stored === 'list' || stored === 'tree') return stored
  } catch {
    // ohne Speicher: Standard je Bildschirmbreite
  }
  return window.matchMedia?.('(max-width: 639px)').matches ? 'list' : 'tree'
}

/** Nur die Abteilung ändern, alles andere am Mitarbeiter bleibt */
const KEEP = { clear_hire_date: false, clear_termination_date: false, clear_birth_date: false, clear_supervisor_id: false }

const message = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback)

/** Organigramm: Abteilungsbaum mit Leitungen, Stellvertretungen und Mitarbeitern – als Baum (Standard)
 *  oder eingerückte Liste. Admin und HR bearbeiten direkt hier (Dialoge, am Desktop auch per Ziehen). */
export function OrgChart() {
  const { isFullHr } = useAuth()
  const query = useOrgChartQuery()
  const departmentsQuery = useDepartmentsQuery(isFullHr)
  const updateDepartment = useUpdateDepartmentMutation()
  const deleteDepartment = useDeleteDepartmentMutation()
  const updateEmployee = useUpdateEmployeeMutation()
  const [search, setSearch] = useState('')
  const [view, setView] = useState<View>(storedView)
  const [dragging, setDragging] = useState<DragItem | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<{ id: number | null; parentId: number | null } | null>(null)
  const [moving, setMoving] = useState<OrgChartPerson | null>(null)
  const [moveError, setMoveError] = useState<string | null>(null)
  const departments = useMemo(() => query.data?.departments ?? [], [query.data])
  const people = useMemo(() => query.data?.people ?? [], [query.data])
  const { roots, unassigned } = useMemo(() => buildOrgTree(departments, people), [departments, people])
  const term = search.trim().toLowerCase()
  const shownRoots = term ? roots.filter((node) => containsMatch(node, term)) : roots
  const nothing = shownRoots.length === 0 && (term ? !unassigned.some((p) => personMatches(p, term)) : unassigned.length === 0)

  function choose(next: View) {
    setView(next)
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      // ohne Speicher (privates Fenster) gilt die Wahl nur bis zum Neuladen
    }
  }

  function moveDepartment(id: number, parentId: number | null) {
    setError(null)
    updateDepartment.mutate(
      { id, payload: parentId === null ? { clear_parent_id: true } : { parent_id: parentId, clear_parent_id: false } },
      { onError: (err) => setError(message(err, 'Verschieben fehlgeschlagen.')) },
    )
  }

  function movePerson(person: OrgChartPerson, departmentId: number | null, onSuccess?: () => void) {
    setError(null)
    setMoveError(null)
    updateEmployee.mutate(
      {
        employeeId: person.employee_id,
        payload: { ...KEEP, department_id: departmentId, clear_department_id: departmentId === null },
      },
      {
        onSuccess,
        onError: (err) => {
          const text = message(err, 'Verschieben fehlgeschlagen.')
          if (moving) setMoveError(text)
          else setError(text)
        },
      },
    )
  }

  const editingApi: OrgEditing = !isFullHr
    ? READ_ONLY
    : {
        canEdit: true,
        dragging,
        startDrag: (item, event) => {
          if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = 'move'
            event.dataTransfer.setData(DRAG_TYPE, JSON.stringify(item))
          }
          setDragging(item)
        },
        endDrag: () => setDragging(null),
        canDrop: (target) => {
          if (!dragging) return false
          if (dragging.kind === 'person') {
            const person = people.find((p) => p.employee_id === dragging.id)
            return person !== undefined && person.department_id !== target
          }
          const department = departments.find((d) => d.id === dragging.id)
          if (!department || department.parent_id === target) return false
          return target === null || !subtreeIds(departments, department.id).has(target)
        },
        drop: (target) => {
          const item = dragging
          setDragging(null)
          if (!item) return
          if (item.kind === 'department') moveDepartment(item.id, target)
          else {
            const person = people.find((p) => p.employee_id === item.id)
            if (person) movePerson(person, target)
          }
        },
        edit: (department) => setEditing({ id: department.id, parentId: department.parent_id }),
        addChild: (department) => setEditing({ id: null, parentId: department.id }),
        remove: (department) => {
          if (!window.confirm(`Abteilung „${department.name}“ löschen? Das geht nur, wenn sie leer ist.`)) return
          setError(null)
          deleteDepartment.mutate(department.id, { onError: (err) => setError(message(err, 'Löschen fehlgeschlagen.')) })
        },
        move: (person) => {
          setMoveError(null)
          setMoving(person)
        },
      }

  const fullDepartments = departmentsQuery.data ?? []
  const dialogDepartment =
    editing === null ? undefined : editing.id === null ? null : (fullDepartments.find((d) => d.id === editing.id) ?? undefined)

  if (query.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (query.isError) return <p className="text-red-600">Das Organigramm konnte nicht geladen werden.</p>
  return (
    <EditingContext.Provider value={editingApi}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="max-w-sm"
            placeholder="Abteilung, Name oder Position suchen"
            aria-label="Im Organigramm suchen"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <div className="flex gap-1" role="group" aria-label="Darstellung">
            {(
              [
                ['tree', 'Baum'],
                ['list', 'Liste'],
              ] as const
            ).map(([kind, label]) => (
              <Button
                key={kind}
                type="button"
                size="sm"
                variant={view === kind ? 'default' : 'outline'}
                aria-pressed={view === kind}
                onClick={() => choose(kind)}
              >
                {label}
              </Button>
            ))}
          </div>
          {isFullHr && (
            <Button type="button" size="sm" variant="outline" onClick={() => setEditing({ id: null, parentId: null })}>
              <Plus className="h-4 w-4" />
              Neue Abteilung
            </Button>
          )}
        </div>
        {isFullHr && (
          <p className="text-xs text-slate-500">
            Bearbeiten über die Symbole an Abteilungen und Personen. Am Computer lassen sich Personen und Abteilungen auch
            mit der Maus auf eine andere Abteilung ziehen.
          </p>
        )}
        {error && (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
        <TopLevelDrop />
        {nothing ? (
          <p className="text-sm text-slate-500">{term ? 'Nichts gefunden.' : 'Noch keine Abteilungen oder Mitarbeiter.'}</p>
        ) : (
          <>
            {view === 'tree' ? (
              <div className="flex flex-col gap-6">
                {shownRoots.map((node) => (
                  <TreeBox key={node.department.id} node={node} query={term} />
                ))}
              </div>
            ) : (
              <ul className="flex flex-col gap-2">
                {shownRoots.map((node) => (
                  <ListNode key={node.department.id} node={node} depth={0} query={term} />
                ))}
              </ul>
            )}
          </>
        )}
        <Unassigned people={unassigned} query={term} />
      </div>
      {isFullHr && (
        <>
          <DepartmentDialog
            department={dialogDepartment}
            parentId={editing?.parentId ?? null}
            departments={fullDepartments}
            onClose={() => setEditing(null)}
          />
          <MovePersonDialog
            person={moving}
            departments={departments}
            onClose={() => setMoving(null)}
            onMove={(person, departmentId) => movePerson(person, departmentId, () => setMoving(null))}
            pending={updateEmployee.isPending}
            error={moveError}
          />
        </>
      )}
    </EditingContext.Provider>
  )
}
