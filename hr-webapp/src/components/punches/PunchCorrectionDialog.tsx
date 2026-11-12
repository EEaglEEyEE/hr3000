import { useEffect, useState, type FormEvent } from 'react'
import { isoToLocalInputValue, localInputValueToIso } from '../../lib/format'
import { PUNCH_TYPE_LABELS } from '../../lib/labels'
import { useCorrectPunchMutation, type Punch } from '../../api/queries/punches'
import type { Project } from '../../api/queries/projects'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface PunchCorrectionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  punch: Punch | undefined
  employeeId: number
  /** Projektzeiten eingeschaltet: Projekt und Tätigkeit am „Kommen“ änderbar. */
  projects?: Project[]
}

export function PunchCorrectionDialog({
  open,
  onOpenChange,
  punch,
  employeeId,
  projects,
}: PunchCorrectionDialogProps) {
  const correctPunch = useCorrectPunchMutation(employeeId)
  const [punchType, setPunchType] = useState<Punch['punch_type']>('COME')
  const [timestamp, setTimestamp] = useState('')
  const [reason, setReason] = useState('')
  const [projectId, setProjectId] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !punch) return
    setPunchType(punch.punch_type)
    setTimestamp(isoToLocalInputValue(punch.timestamp_utc))
    setReason('')
    setProjectId(punch.project_id != null ? String(punch.project_id) : '')
    setNote(punch.activity_note ?? '')
    setError(null)
  }, [open, punch])
  const withProject = projects !== undefined && punchType === 'COME'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!punch) return
    setError(null)
    try {
      await correctPunch.mutateAsync({
        punchId: punch.id,
        payload: {
          punch_type: punchType,
          timestamp_utc: localInputValueToIso(timestamp),
          correction_reason: reason,
          ...(withProject ? { project_id: projectId ? Number(projectId) : null, activity_note: note.trim() || null } : {}),
        },
      })
      onOpenChange(false)
    } catch {
      setError('Korrektur fehlgeschlagen.')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Stempelung korrigieren</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label>Art</Label>
            <Select value={punchType} onValueChange={(value) => setPunchType(value as Punch['punch_type'])}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(PUNCH_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="timestamp">Zeitpunkt</Label>
            <Input
              id="timestamp"
              type="datetime-local"
              required
              value={timestamp}
              onChange={(event) => setTimestamp(event.target.value)}
            />
          </div>
          {withProject && (
            <>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="punch-project">Projekt</Label>
                <select
                  id="punch-project"
                  className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
                  value={projectId}
                  onChange={(event) => setProjectId(event.target.value)}
                >
                  <option value="">Ohne Projekt</option>
                  {projects!.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.number ? `${project.number} ` : ''}
                      {project.name}
                      {project.active ? '' : ' (inaktiv)'}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="punch-note">Tätigkeit</Label>
                <Input id="punch-note" maxLength={200} value={note} onChange={(event) => setNote(event.target.value)} />
              </div>
            </>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reason">Begründung</Label>
            <Input
              id="reason"
              required
              placeholder="z. B. Tablet-Uhr war falsch gestellt"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={correctPunch.isPending}>
              {correctPunch.isPending ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
