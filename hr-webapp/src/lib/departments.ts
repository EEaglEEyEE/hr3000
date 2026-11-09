/** Abteilungen als Baum (parent_id): Pfade wie „Vertrieb › Innendienst“ für Auswahllisten und Tooltips. */
export type DepartmentNode = { id: number; name: string; parent_id?: number | null }

export function departmentPaths(departments: DepartmentNode[]): Map<number, string> {
  const byId = new Map(departments.map((department) => [department.id, department]))
  const paths = new Map<number, string>()
  for (const department of departments) {
    const names: string[] = []
    const seen = new Set<number>()
    let current: DepartmentNode | undefined = department
    // Zyklen oder verwaiste Verweise beenden den Pfad statt endlos zu laufen
    while (current && !seen.has(current.id)) {
      seen.add(current.id)
      names.unshift(current.name)
      current = current.parent_id != null ? byId.get(current.parent_id) : undefined
    }
    paths.set(department.id, names.join(' › '))
  }
  return paths
}

type LeaderInfo = { employee_id: number; name: string; role: string; active: boolean }
type DepartmentWithLeaders = { id: number; name: string; parent_id: number | null; leaders?: LeaderInfo[] }

const activeHeads = (department: DepartmentWithLeaders) =>
  (department.leaders ?? []).filter((leader) => leader.role === 'HEAD' && leader.active)

/** Text zur automatischen Führungskraft (wie org_service im Backend): die Leitungen der eigenen
 *  Abteilung – ohne Abteilung der ersten, die die Person leitet –, ist die Person selbst Leitung oder
 *  hat die Abteilung keine, die der nächsten darüber. Stellvertretungen werden mit genannt. */
export function automaticSupervisorText(
  departments: DepartmentWithLeaders[],
  departmentId: number | null,
  employeeId: number | undefined,
): string {
  const byId = new Map(departments.map((d) => [d.id, d]))
  const ledByEmployee = departments
    .filter((d) => employeeId !== undefined && activeHeads(d).some((h) => h.employee_id === employeeId))
    .sort((a, b) => a.id - b.id)
  const start = departmentId ?? ledByEmployee[0]?.id ?? null
  const seen = new Set<number>()
  let current = start != null ? byId.get(start) : undefined
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    const heads = activeHeads(current)
    if (heads.length > 0 && !heads.some((h) => h.employee_id === employeeId)) {
      const deputies = (current.leaders ?? []).filter(
        (l) => l.role === 'DEPUTY' && l.active && l.employee_id !== employeeId,
      )
      const deputyText = deputies.length > 0 ? ` Stellvertretung: ${deputies.map((d) => d.name).join(', ')}.` : ''
      return `Automatisch: ${heads.map((h) => h.name).join(', ')} (Leitung ${current.name}).${deputyText}`
    }
    current = current.parent_id != null ? byId.get(current.parent_id) : undefined
  }
  return start == null ? 'Automatisch: keine (ohne Abteilung).' : 'Automatisch: keine (Abteilung ohne Leitung).'
}
