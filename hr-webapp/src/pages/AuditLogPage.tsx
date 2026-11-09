import { useState } from 'react'
import { Download } from 'lucide-react'
import { downloadCsv } from '../lib/csv'
import { Button } from '../components/ui/button'
import { useAuditLogQuery } from '../api/queries/auditLog'
import { AUDIT_ACTION_LABELS, AUDIT_ENTITY_TYPE_LABELS } from '../lib/labels'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

const ALL_ENTITY_TYPES = '__all__'

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' })
}

export function AuditLogPage() {
  const [entityType, setEntityType] = useState(ALL_ENTITY_TYPES)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const auditLogQuery = useAuditLogQuery({
    entityType: entityType === ALL_ENTITY_TYPES ? undefined : entityType,
    from: dateFrom || undefined,
    to: dateTo || undefined,
  })

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Audit-Protokoll</h1>
        <p className="text-sm text-slate-500">
          Wer wann was geändert hat – z. B. Stempelungen, Mitarbeiter, Rollen, Abwesenheiten, Dokumente, Monatsabschlüsse
          und Einstellungen – sowie Anmeldungen in der Webapp (ohne IP-Adresse). „CSV exportieren“ speichert die angezeigten
          Einträge (höchstens 500; für mehr den Zeitraum eingrenzen).
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Entität</Label>
          <Select value={entityType} onValueChange={setEntityType}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_ENTITY_TYPES}>Alle</SelectItem>
              {Object.entries(AUDIT_ENTITY_TYPE_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="date_from">Von</Label>
          <Input id="date_from" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="date_to">Bis</Label>
          <Input id="date_to" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </div>
        <Button
          variant="outline"
          disabled={!auditLogQuery.data?.length}
          onClick={() =>
            downloadCsv(
              `audit-protokoll${dateFrom ? `_${dateFrom}` : ''}${dateTo ? `_${dateTo}` : ''}.csv`,
              ['Zeitpunkt', 'Person', 'Aktion', 'Bereich', 'ID', 'Detail'],
              (auditLogQuery.data ?? []).map((entry) => [
                formatTimestamp(entry.created_at),
                entry.actor_label,
                AUDIT_ACTION_LABELS[entry.action],
                AUDIT_ENTITY_TYPE_LABELS[entry.entity_type] ?? entry.entity_type,
                entry.entity_id,
                entry.detail,
              ]),
            )
          }
        >
          <Download className="h-4 w-4" />
          CSV exportieren
        </Button>
      </div>

      {auditLogQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {auditLogQuery.isError && <p className="text-red-600">Einträge konnten nicht geladen werden.</p>}

      {auditLogQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Zeitpunkt</TableHead>
              <TableHead>Akteur</TableHead>
              <TableHead>Aktion</TableHead>
              <TableHead>Entität</TableHead>
              <TableHead>Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {auditLogQuery.data.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell className="whitespace-nowrap text-slate-500">
                  {formatTimestamp(entry.created_at)}
                </TableCell>
                <TableCell>{entry.actor_label}</TableCell>
                <TableCell>{AUDIT_ACTION_LABELS[entry.action]}</TableCell>
                <TableCell className="text-slate-500">
                  {AUDIT_ENTITY_TYPE_LABELS[entry.entity_type] ?? entry.entity_type} #{entry.entity_id}
                </TableCell>
                <TableCell className="text-slate-500">{entry.detail ?? '–'}</TableCell>
              </TableRow>
            ))}
            {auditLogQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-slate-500">
                  Keine Einträge im gewählten Zeitraum.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
