import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useOrgChartQuery, type OrgChartPerson } from '../../api/queries/departments'
import { Input } from '../ui/input'

interface Node {
  person: OrgChartPerson
  children: Node[]
  size: number
}

function buildTree(people: OrgChartPerson[]): Node[] {
  const byId = new Map(people.map((person) => [person.employee_id, person]))
  const children = new Map<number | null, OrgChartPerson[]>()
  for (const person of people) {
    const parent = person.supervisor_id !== null && byId.has(person.supervisor_id) ? person.supervisor_id : null
    children.set(parent, [...(children.get(parent) ?? []), person])
  }
  const build = (parent: number | null, seen: Set<number>): Node[] =>
    (children.get(parent) ?? [])
      .filter((person) => !seen.has(person.employee_id))
      .map((person) => {
        const nested = build(person.employee_id, new Set([...seen, person.employee_id]))
        return { person, children: nested, size: nested.reduce((sum, child) => sum + 1 + child.size, 0) }
      })
      // Führungskräfte mit großen Bereichen zuerst, sonst alphabetisch
      .sort((a, b) => b.size - a.size || a.person.last_name.localeCompare(b.person.last_name))
  return build(null, new Set())
}

function matches(person: OrgChartPerson, query: string): boolean {
  const text = `${person.first_name} ${person.last_name} ${person.position ?? ''} ${person.department ?? ''}`.toLowerCase()
  return text.includes(query)
}

function containsMatch(node: Node, query: string): boolean {
  return matches(node.person, query) || node.children.some((child) => containsMatch(child, query))
}

function NodeView({ node, depth, query }: { node: Node; depth: number; query: string }) {
  const [open, setOpen] = useState(depth < 2)
  const visibleChildren = query ? node.children.filter((child) => containsMatch(child, query)) : node.children
  const expanded = query ? visibleChildren.length > 0 : open
  const hit = query !== '' && matches(node.person, query)
  return (
    <li className="flex flex-col gap-2">
      <div
        className={`flex items-start gap-2 rounded-md border bg-white px-3 py-2 ${hit ? 'border-sky-500' : 'border-slate-200'}`}
      >
        {node.children.length > 0 ? (
          <button
            type="button"
            className="mt-0.5 text-slate-500 hover:text-slate-900"
            onClick={() => setOpen(!open)}
            aria-label={expanded ? 'Zuklappen' : 'Aufklappen'}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        ) : (
          <span className="w-4" />
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900">
            {node.person.first_name} {node.person.last_name}
          </p>
          <p className="truncate text-xs text-slate-500">
            {[node.person.position, node.person.department].filter(Boolean).join(' · ') || '–'}
          </p>
        </div>
        {node.size > 0 && (
          <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600" title="Mitarbeiter im Bereich">
            {node.size}
          </span>
        )}
      </div>
      {expanded && visibleChildren.length > 0 && (
        <ul className="ml-3 flex flex-col gap-2 border-l border-slate-200 pl-3">
          {visibleChildren.map((child) => (
            <NodeView key={child.person.employee_id} node={child} depth={depth + 1} query={query} />
          ))}
        </ul>
      )}
    </li>
  )
}

/** Organigramm aus der Führungskraft je Mitarbeiter: oben stehen alle ohne (aktive) Führungskraft. */
export function OrgChart() {
  const query = useOrgChartQuery()
  const [search, setSearch] = useState('')
  const tree = useMemo(() => buildTree(query.data ?? []), [query.data])
  const term = search.trim().toLowerCase()
  const roots = term ? tree.filter((node) => containsMatch(node, term)) : tree

  if (query.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (query.isError) return <p className="text-red-600">Das Organigramm konnte nicht geladen werden.</p>
  return (
    <div className="flex flex-col gap-4">
      <Input
        className="max-w-sm"
        placeholder="Name, Position oder Abteilung suchen"
        aria-label="Im Organigramm suchen"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {roots.length === 0 ? (
        <p className="text-sm text-slate-500">{term ? 'Niemand gefunden.' : 'Noch keine Mitarbeiter.'}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {roots.map((node) => (
            <NodeView key={node.person.employee_id} node={node} depth={0} query={term} />
          ))}
        </ul>
      )}
    </div>
  )
}
