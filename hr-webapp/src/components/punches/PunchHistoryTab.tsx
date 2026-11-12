import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useDeletePunchMutation, useEmployeePunchesQuery, type Punch } from '../../api/queries/punches'
import { useProjectsQuery } from '../../api/queries/projects'
import { useFeaturesQuery } from '../../api/queries/workTimeModel'
import { formatDateTime } from '../../lib/format'
import { PUNCH_SOURCE_LABELS, PUNCH_SOURCE_VARIANT, PUNCH_TYPE_LABELS } from '../../lib/labels'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { PunchCorrectionDialog } from './PunchCorrectionDialog'
import { PunchCreateDialog } from './PunchCreateDialog'

/** Kennzeichen der Standortprüfung beim Stempeln im Web-Login („innerhalb“ bleibt ohne Kennzeichen). */
export function LocationCheckBadge({ check }: { check: Punch['location_check'] }) {
  if (check === 'OUTSIDE') {
    return (
      <Badge variant="danger" title="Im Web-Login außerhalb der Firmenstandorte gestempelt (gespeichert ist nur das Ergebnis, keine Koordinaten)">
        außerhalb
      </Badge>
    )
  }
  if (check === 'UNKNOWN') {
    return (
      <Badge variant="warning" title="Standort beim Stempeln nicht freigegeben oder zu ungenau">
        Standort unbekannt
      </Badge>
    )
  }
  return null
}

export function PunchHistoryTab({
  employeeId,
  readOnly = false,
}: {
  employeeId: number
  readOnly?: boolean
}) {
  const punchesQuery = useEmployeePunchesQuery(employeeId)
  const deletePunch = useDeletePunchMutation(employeeId)
  // Projektzeiten: Projekt am „Kommen“ anzeigen und beim Korrigieren ändern (nur Verwaltung)
  const projectsEnabled = useFeaturesQuery(!readOnly).data?.project_times_enabled === true
  const projects = useProjectsQuery(!readOnly && projectsEnabled).data
  const projectLabel = (punch: Punch) => {
    if (punch.project_id == null) return null
    const project = projects?.find((p) => p.id === punch.project_id)
    const name = project ? `${project.number ? `${project.number} ` : ''}${project.name}` : `Projekt ${punch.project_id}`
    return punch.activity_note ? `${name} – ${punch.activity_note}` : name
  }
  const [selectedPunch, setSelectedPunch] = useState<Punch | undefined>(undefined)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [deleteCandidate, setDeleteCandidate] = useState<Punch | undefined>(undefined)

  function openCorrectionDialog(punch: Punch) {
    setSelectedPunch(punch)
    setDialogOpen(true)
  }

  async function confirmDelete() {
    if (!deleteCandidate) return
    await deletePunch.mutateAsync(deleteCandidate.id)
    setDeleteCandidate(undefined)
  }

  if (punchesQuery.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (punchesQuery.isError) return <p className="text-red-600">Punches konnten nicht geladen werden.</p>

  const punches = [...(punchesQuery.data ?? [])].sort((a, b) => b.timestamp_utc.localeCompare(a.timestamp_utc))

  return (
    <div className="flex flex-col gap-4">
      {!readOnly && (
        <div>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Stempelung nachtragen
          </Button>
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Zeitpunkt</TableHead>
            <TableHead>Art</TableHead>
            <TableHead>Quelle</TableHead>
            <TableHead>Korrigiert</TableHead>
            {!readOnly && <TableHead />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {punches.map((punch) => (
            <TableRow key={punch.id}>
              <TableCell>{formatDateTime(punch.timestamp_utc)}</TableCell>
              <TableCell>
                {PUNCH_TYPE_LABELS[punch.punch_type]}
                {projectsEnabled && projectLabel(punch) && <div className="text-xs text-slate-500">{projectLabel(punch)}</div>}
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  <Badge variant={PUNCH_SOURCE_VARIANT[punch.source]}>
                    {PUNCH_SOURCE_LABELS[punch.source]}
                  </Badge>
                  <LocationCheckBadge check={punch.location_check} />
                </div>
              </TableCell>
              <TableCell>
                {punch.corrected ? (
                  <span title={punch.correction_reason ?? undefined}>
                    <Badge variant="warning">Ja</Badge>
                  </span>
                ) : (
                  '–'
                )}
              </TableCell>
              {!readOnly && (
                <TableCell>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => openCorrectionDialog(punch)}>
                      Korrigieren
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteCandidate(punch)}>
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </div>
                </TableCell>
              )}
            </TableRow>
          ))}
          {punches.length === 0 && (
            <TableRow>
              <TableCell colSpan={readOnly ? 4 : 5} className="text-center text-slate-500">
                Keine Zeiterfassung vorhanden.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {!readOnly && (
        <>
          <PunchCorrectionDialog
            open={dialogOpen}
            onOpenChange={setDialogOpen}
            punch={selectedPunch}
            employeeId={employeeId}
            projects={projectsEnabled ? (projects ?? []) : undefined}
          />
          <PunchCreateDialog
            open={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            employeeId={employeeId}
          />
          <Dialog
            open={deleteCandidate !== undefined}
            onOpenChange={(open) => !open && setDeleteCandidate(undefined)}
          >
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Stempelung löschen</DialogTitle>
              </DialogHeader>
              <p className="text-sm text-slate-600">
                {deleteCandidate && (
                  <>
                    {PUNCH_TYPE_LABELS[deleteCandidate.punch_type]} um{' '}
                    {formatDateTime(deleteCandidate.timestamp_utc)} wirklich endgültig löschen? Das
                    kann nicht widerrufen werden.
                  </>
                )}
              </p>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDeleteCandidate(undefined)}>
                  Abbrechen
                </Button>
                <Button
                  variant="destructive"
                  disabled={deletePunch.isPending}
                  onClick={confirmDelete}
                >
                  {deletePunch.isPending ? 'Löschen…' : 'Endgültig löschen'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </>
      )}
    </div>
  )
}
