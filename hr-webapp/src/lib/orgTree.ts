/** Organigramm als Abteilungsbaum: je Abteilung Leitungen, Stellvertretungen, Mitarbeiter (ohne
 *  Leitungen und Stellvertretungen dieser Abteilung) und Unterabteilungen; dazu alle ohne Abteilung. */
import type { DeputyRights, LeaderRole } from './leaders'

export type OrgLeader = { employee_id: number; role: LeaderRole; deputy_rights: DeputyRights }
export type OrgDepartment = { id: number; name: string; parent_id: number | null; leaders: OrgLeader[] }
export type OrgPerson = {
  employee_id: number
  first_name: string
  last_name: string
  position: string | null
  department_id: number | null
}

export interface OrgNode<P extends OrgPerson = OrgPerson> {
  department: OrgDepartment
  heads: P[]
  deputies: { person: P; rights: DeputyRights }[]
  members: P[]
  children: OrgNode<P>[]
  /** Personen in der Abteilung und allen darunter (Leitungen und Stellvertretungen eingeschlossen) */
  size: number
}

export function personMatches(person: OrgPerson | null, query: string): boolean {
  if (!person) return false
  return `${person.first_name} ${person.last_name} ${person.position ?? ''}`.toLowerCase().includes(query)
}

export function buildOrgTree<P extends OrgPerson>(
  departments: OrgDepartment[],
  people: P[],
): { roots: OrgNode<P>[]; unassigned: P[] } {
  const ids = new Set(departments.map((d) => d.id))
  const byPerson = new Map(people.map((p) => [p.employee_id, p]))
  const children = new Map<number | null, OrgDepartment[]>()
  for (const department of departments) {
    const parent = department.parent_id !== null && ids.has(department.parent_id) ? department.parent_id : null
    children.set(parent, [...(children.get(parent) ?? []), department])
  }
  const leaders = new Set(departments.flatMap((d) => d.leaders.map((l) => l.employee_id)))
  const build = (parent: number | null, seen: Set<number>): OrgNode<P>[] =>
    [...(children.get(parent) ?? [])]
      .filter((department) => !seen.has(department.id))
      .sort((a, b) => a.name.localeCompare(b.name, 'de'))
      .map((department) => {
        const heads = department.leaders
          .filter((l) => l.role === 'HEAD')
          .map((l) => byPerson.get(l.employee_id))
          .filter((p): p is P => p !== undefined)
        const deputies = department.leaders
          .filter((l) => l.role === 'DEPUTY')
          .flatMap((l) => {
            const person = byPerson.get(l.employee_id)
            return person ? [{ person, rights: l.deputy_rights }] : []
          })
        const own = new Set(department.leaders.map((l) => l.employee_id))
        const members = people.filter((p) => p.department_id === department.id && !own.has(p.employee_id))
        const nested = build(department.id, new Set([...seen, department.id]))
        const size = heads.length + deputies.length + members.length
        return { department, heads, deputies, members, children: nested, size: size + nested.reduce((sum, child) => sum + child.size, 0) }
      })
  // Ohne Abteilung: wer weder einer Abteilung angehört noch eine leitet oder vertritt
  const unassigned = people.filter((p) => p.department_id === null && !leaders.has(p.employee_id))
  return { roots: build(null, new Set()), unassigned }
}

/** Die Abteilung und alle darunter (z. B. damit eine Abteilung nicht unter sich selbst landet). */
export function subtreeIds(departments: { id: number; parent_id: number | null }[], rootId: number): Set<number> {
  const result = new Set<number>([rootId])
  let grew = true
  while (grew) {
    grew = false
    for (const department of departments) {
      if (department.parent_id !== null && result.has(department.parent_id) && !result.has(department.id)) {
        result.add(department.id)
        grew = true
      }
    }
  }
  return result
}
