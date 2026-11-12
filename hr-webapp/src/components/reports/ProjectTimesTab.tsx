import { useState } from 'react'
import { useProjectTimesQuery, type ProjectTimeRow } from '../../api/queries/projects'
import { downloadCsv } from '../../lib/csv'
import { currentYearMonth, formatHoursMinutes, monthRange } from '../../lib/format'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

type GroupBy = 'project' | 'customer' | 'employee'

const GROUP_LABELS: Record<GroupBy, string> = { project: 'Projekt', customer: 'Kunde', employee: 'Mitarbeiter' }

function projectName(row: ProjectTimeRow): string {
  return row.project_number ? `${row.project_number} ${row.project_name}` : row.project_name
}

function groupKey(row: ProjectTimeRow, by: GroupBy): string {
  if (by === 'project') return projectName(row)
  if (by === 'customer') return row.customer_name ?? 'Ohne Kunde'
  return `${row.last_name}, ${row.first_name}`
}

interface Group {
  label: string
  minutes: number
  billable: number
  rows: ProjectTimeRow[]
}

/** Gruppiert nach Projekt, Kunde oder Mitarbeiter – Summe und abrechenbarer Anteil je Gruppe. */
function groupProjectTimes(rows: ProjectTimeRow[], by: GroupBy): Group[] {
  const groups = new Map<string, Group>()
  for (const row of rows) {
    const label = groupKey(row, by)
    const group = groups.get(label) ?? { label, minutes: 0, billable: 0, rows: [] }
    group.minutes += row.minutes
    if (row.billable) group.billable += row.minutes
    group.rows.push(row)
    groups.set(label, group)
  }
  return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label, 'de'))
}

const hours = (minutes: number) => (minutes / 60).toFixed(2)

/** Analysen → „Projektzeiten“: Summe je Projekt, Kunde oder Mitarbeiter, abrechenbar getrennt. */
export function ProjectTimesTab() {
  const initial = monthRange(currentYearMonth())
  const [from, setFrom] = useState(initial.from)
  const [to, setTo] = useState(initial.to)
  const [by, setBy] = useState<GroupBy>('project')
  const query = useProjectTimesQuery(from, to)
  const data = query.data
  const groups = groupProjectTimes(data?.rows ?? [], by)

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-500">
        Selbst eingetragene Zeiten mit Projekt, je Spanne ohne die Pausen darin. Die gesetzliche Mindestpause der
        Tagesberechnung wird nicht auf Projekte verteilt.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Von
          <Input type="date" className="w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Bis
          <Input type="date" className="w-40" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          Gruppieren nach
          <div className="flex gap-1" role="group" aria-label="Gruppieren nach">
            {(Object.keys(GROUP_LABELS) as GroupBy[]).map((key) => (
              <Button key={key} size="sm" variant={by === key ? 'default' : 'outline'} onClick={() => setBy(key)}>
                {GROUP_LABELS[key]}
              </Button>
            ))}
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={!data || data.rows.length === 0}
          onClick={() =>
            downloadCsv(
              'projektzeiten.csv',
              ['Projektnummer', 'Projekt', 'Kunde', 'Kostenstelle', 'Abrechenbar', 'Personalnummer', 'Nachname', 'Vorname', 'Stunden'],
              (data?.rows ?? []).map((r) => [
                r.project_number, r.project_name, r.customer_name, r.cost_center, r.billable ? 'ja' : 'nein',
                r.employee_number, r.last_name, r.first_name, hours(r.minutes),
              ]),
            )
          }
        >
          CSV exportieren
        </Button>
      </div>
      {query.isLoading && <p className="text-slate-500">Lädt…</p>}
      {query.isError && <p className="text-red-600">{query.error instanceof Error ? query.error.message : 'Auswertung konnte nicht geladen werden.'}</p>}
      {data && (
        <>
          <div className="flex flex-wrap gap-4 text-sm text-slate-700">
            <span>Gesamt: {formatHoursMinutes(data.total_minutes)} Std.</span>
            <span>Abrechenbar: {formatHoursMinutes(data.billable_minutes)} Std.</span>
            <span>Nicht abrechenbar: {formatHoursMinutes(data.non_billable_minutes)} Std.</span>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{GROUP_LABELS[by]}</TableHead>
                <TableHead>Details</TableHead>
                <TableHead className="text-right">Abrechenbar</TableHead>
                <TableHead className="text-right">Stunden</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.map((group) => (
                <TableRow key={group.label}>
                  <TableCell className="font-medium">{group.label}</TableCell>
                  <TableCell className="text-sm text-slate-600">
                    {group.rows
                      .map((r) => (by === 'employee' ? projectName(r) : `${r.last_name}, ${r.first_name}${by === 'customer' ? ` (${projectName(r)})` : ''}`) + `: ${formatHoursMinutes(r.minutes)}`)
                      .join(' · ')}
                  </TableCell>
                  <TableCell className="text-right">
                    {group.billable === group.minutes ? (
                      <Badge variant="success">alles</Badge>
                    ) : group.billable === 0 ? (
                      <Badge>nichts</Badge>
                    ) : (
                      `${formatHoursMinutes(group.billable)} Std.`
                    )}
                  </TableCell>
                  <TableCell className="text-right">{formatHoursMinutes(group.minutes)}</TableCell>
                </TableRow>
              ))}
              {groups.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-slate-500">
                    Keine Projektzeiten im Zeitraum.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </>
      )}
    </div>
  )
}
