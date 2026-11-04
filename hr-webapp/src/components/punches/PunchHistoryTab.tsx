import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useDeletePunchMutation, useEmployeePunchesQuery, type Punch } from '../../api/queries/punches'
import { formatDateTime } from '../../lib/format'
import { PUNCH_SOURCE_LABELS, PUNCH_SOURCE_VARIANT, PUNCH_TYPE_LABELS } from '../../lib/labels'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { PunchCorrectionDialog } from './PunchCorrectionDialog'
import { PunchCreateDialog } from './PunchCreateDialog'

export function PunchHistoryTab({
  employeeId,
  readOnly = false,
}: {
  employeeId: number
  readOnly?: boolean
}) {
  const punchesQuery = useEmployeePunchesQuery(employeeId)
  const deletePunch = useDeletePunchMutation(employeeId)
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
              <TableCell>{PUNCH_TYPE_LABELS[punch.punch_type]}</TableCell>
              <TableCell>
                <Badge variant={PUNCH_SOURCE_VARIANT[punch.source]}>
                  {PUNCH_SOURCE_LABELS[punch.source]}
                </Badge>
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
