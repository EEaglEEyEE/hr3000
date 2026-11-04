import { useEffect, useState, type FormEvent } from 'react'
import { useCreateDefaultShiftMutation } from '../../api/queries/employeeDefaultShifts'
import { useShiftTemplatesQuery } from '../../api/queries/shiftTemplates'
import { ApiError } from '../../api/client'
import { todayIsoDate } from '../../lib/format'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface DefaultShiftFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  employeeId: number
}

const WEEKDAYS = [
  { bit: 1 << 0, label: 'Mo' },
  { bit: 1 << 1, label: 'Di' },
  { bit: 1 << 2, label: 'Mi' },
  { bit: 1 << 3, label: 'Do' },
  { bit: 1 << 4, label: 'Fr' },
  { bit: 1 << 5, label: 'Sa' },
  { bit: 1 << 6, label: 'So' },
]

const MO_FR = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)

export function DefaultShiftFormDialog({ open, onOpenChange, employeeId }: DefaultShiftFormDialogProps) {
  const createDefaultShift = useCreateDefaultShiftMutation(employeeId)
  const templatesQuery = useShiftTemplatesQuery()
  const templates = templatesQuery.data ?? []

  const [validFrom, setValidFrom] = useState(todayIsoDate())
  const [shiftTemplateId, setShiftTemplateId] = useState('')
  const [weekdaysMask, setWeekdaysMask] = useState(MO_FR)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setValidFrom(todayIsoDate())
    setShiftTemplateId('')
    setWeekdaysMask(MO_FR)
    setError(null)
  }, [open])

  function toggleWeekday(bit: number) {
    setWeekdaysMask((mask) => (mask & bit ? mask & ~bit : mask | bit))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      await createDefaultShift.mutateAsync({
        shift_template_id: Number(shiftTemplateId),
        valid_from: validFrom,
        weekdays_mask: weekdaysMask,
        flexible: false,
        on_demand: false,
      })
      onOpenChange(false)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'OVERLAPPING_PERIOD') {
        setError('Der Zeitraum überlappt mit einer bestehenden Standard-Schicht.')
      } else if (err instanceof ApiError && err.code === 'REST_PERIOD_VIOLATION') {
        setError('Die gesetzliche Mindestruhezeit von 11 Stunden (§5 ArbZG) wird unterschritten.')
      } else if (err instanceof ApiError && err.code === 'MAX_DAILY_WORKING_TIME_EXCEEDED') {
        setError('Die Schicht überschreitet die gesetzliche Höchstarbeitszeit von 10 Stunden pro Tag (§3 ArbZG).')
      } else {
        setError('Speichern fehlgeschlagen.')
      }
    }
  }

  const isSubmitting = createDefaultShift.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Neue Standard-Schicht</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="default_shift_valid_from">Gültig ab</Label>
            <Input
              id="default_shift_valid_from"
              type="date"
              required
              value={validFrom}
              onChange={(event) => setValidFrom(event.target.value)}
            />
            <p className="text-xs text-slate-500">
              Eine bestehende, noch offene Standard-Schicht wird automatisch bis zum Vortag begrenzt.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Schichtvorlage</Label>
            <Select value={shiftTemplateId} onValueChange={setShiftTemplateId}>
              <SelectTrigger>
                <SelectValue placeholder="Vorlage wählen" />
              </SelectTrigger>
              <SelectContent>
                {templates.map((template) => (
                  <SelectItem key={template.id} value={String(template.id)}>
                    {template.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {templates.length === 0 && !templatesQuery.isLoading && (
              <p className="text-xs text-slate-500">
                Noch keine Schichtvorlagen angelegt (siehe Seite „Schichtvorlagen“).
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Wochentage</Label>
            <div className="flex gap-1">
              {WEEKDAYS.map(({ bit, label }) => (
                <button
                  key={bit}
                  type="button"
                  onClick={() => toggleWeekday(bit)}
                  className={
                    'h-9 w-9 rounded-md border text-sm font-medium ' +
                    (weekdaysMask & bit
                      ? 'border-slate-900 bg-slate-900 text-white'
                      : 'border-slate-200 bg-white text-slate-600')
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isSubmitting || !shiftTemplateId || weekdaysMask === 0}>
              {isSubmitting ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
