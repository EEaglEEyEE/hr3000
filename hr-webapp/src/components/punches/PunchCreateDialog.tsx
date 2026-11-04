import { useEffect, useState, type FormEvent } from 'react'
import { useCreatePunchMutation } from '../../api/queries/punches'
import type { Punch } from '../../api/queries/punches'
import { localInputValueToIso, todayIsoDate } from '../../lib/format'
import { PUNCH_TYPE_LABELS } from '../../lib/labels'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface PunchCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  employeeId: number
}

export function PunchCreateDialog({ open, onOpenChange, employeeId }: PunchCreateDialogProps) {
  const createPunch = useCreatePunchMutation(employeeId)
  const [punchType, setPunchType] = useState<Punch['punch_type']>('COME')
  const [timestamp, setTimestamp] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setPunchType('COME')
    setTimestamp(`${todayIsoDate()}T08:00`)
    setError(null)
  }, [open])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      await createPunch.mutateAsync({
        employee_id: employeeId,
        punch_type: punchType,
        timestamp_utc: localInputValueToIso(timestamp),
        idempotency_key: crypto.randomUUID(),
      })
      onOpenChange(false)
    } catch {
      setError('Nachtragen fehlgeschlagen.')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Stempelung nachtragen</DialogTitle>
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
            <Label htmlFor="new_timestamp">Zeitpunkt</Label>
            <Input
              id="new_timestamp"
              type="datetime-local"
              required
              value={timestamp}
              onChange={(event) => setTimestamp(event.target.value)}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={createPunch.isPending}>
              {createPunch.isPending ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
