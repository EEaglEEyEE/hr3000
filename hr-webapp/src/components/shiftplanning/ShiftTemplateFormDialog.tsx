import { useEffect, useState, type FormEvent } from 'react'
import {
  useCreateShiftTemplateMutation,
  useUpdateShiftTemplateMutation,
  type BreakMode,
  type ShiftTemplate,
  type TargetPeriod,
} from '../../api/queries/shiftTemplates'
import { todayIsoDate } from '../../lib/format'
import { ApiError } from '../../api/client'
import type { Location } from '../../api/queries/locations'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface ShiftTemplateFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  template?: ShiftTemplate
  locations: Location[]
}

const ALL_LOCATIONS = '__all__'

export function ShiftTemplateFormDialog({
  open,
  onOpenChange,
  template,
  locations,
}: ShiftTemplateFormDialogProps) {
  const isEditMode = template !== undefined
  const createTemplate = useCreateShiftTemplateMutation()
  const updateTemplate = useUpdateShiftTemplateMutation()

  const [name, setName] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [breakMode, setBreakMode] = useState<BreakMode>('FLEXIBLE')
  const [fixedBreakStart, setFixedBreakStart] = useState('')
  const [fixedBreakEnd, setFixedBreakEnd] = useState('')
  const [minBreakMinutes, setMinBreakMinutes] = useState<number | ''>('')
  const [targetMinutes, setTargetMinutes] = useState(480)
  const [targetPeriod, setTargetPeriod] = useState<TargetPeriod>('DAILY')
  const [locationId, setLocationId] = useState(ALL_LOCATIONS)
  const [validFrom, setValidFrom] = useState(todayIsoDate())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(template?.name ?? '')
    setStartTime(template?.start_time?.slice(0, 5) ?? '')
    setEndTime(template?.end_time?.slice(0, 5) ?? '')
    setBreakMode(template?.break_mode ?? 'FLEXIBLE')
    setFixedBreakStart(template?.fixed_break_start?.slice(0, 5) ?? '')
    setFixedBreakEnd(template?.fixed_break_end?.slice(0, 5) ?? '')
    setMinBreakMinutes(template?.min_break_minutes ?? '')
    setTargetMinutes(template?.target_minutes ?? 480)
    setTargetPeriod(template?.target_period ?? 'DAILY')
    setLocationId(template?.location_id ? String(template.location_id) : ALL_LOCATIONS)
    setValidFrom(todayIsoDate())
    setError(null)
  }, [open, template])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const selectedLocationId = locationId === ALL_LOCATIONS ? undefined : Number(locationId)
    const payload = {
      name,
      start_time: startTime || null,
      end_time: endTime || null,
      break_mode: breakMode,
      fixed_break_start: breakMode === 'FIXED' ? fixedBreakStart || null : null,
      fixed_break_end: breakMode === 'FIXED' ? fixedBreakEnd || null : null,
      // 0 = keine eigene Pause (es gelten die Pausenregeln); leer lassen entfernt eine bisherige.
      min_break_minutes: breakMode === 'FLEXIBLE' ? (minBreakMinutes === '' ? 0 : minBreakMinutes) : null,
      target_minutes: targetMinutes,
      target_period: targetPeriod,
      location_id: selectedLocationId,
    }
    try {
      if (isEditMode) {
        await updateTemplate.mutateAsync({
          templateId: template.id,
          payload: { ...payload, clear_location_id: selectedLocationId === undefined, valid_from: validFrom },
        })
      } else {
        await createTemplate.mutateAsync(payload)
      }
      onOpenChange(false)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'NAME_TAKEN') {
        setError('Eine Schichtvorlage mit diesem Namen existiert bereits.')
      } else if (err instanceof ApiError && err.status !== 422) {
        setError(err.message)
      } else {
        setError('Speichern fehlgeschlagen.')
      }
    }
  }

  const isSubmitting = createTemplate.isPending || updateTemplate.isPending
  const targetChanged = isEditMode && (targetMinutes !== template.target_minutes || targetPeriod !== template.target_period)
  const breakChanged =
    isEditMode &&
    (breakMode !== template.break_mode ||
      (breakMode === 'FIXED'
        ? fixedBreakStart !== (template.fixed_break_start?.slice(0, 5) ?? '') ||
          fixedBreakEnd !== (template.fixed_break_end?.slice(0, 5) ?? '')
        : (minBreakMinutes || 0) !== (template.min_break_minutes || 0)))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Schichtvorlage bearbeiten' : 'Neue Schichtvorlage'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="shift_template_name">Name</Label>
            <Input
              id="shift_template_name"
              required
              placeholder="z.B. Frühschicht"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="start_time">Beginn</Label>
              <Input
                id="start_time"
                type="time"
                value={startTime}
                onChange={(event) => setStartTime(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="end_time">Ende</Label>
              <Input
                id="end_time"
                type="time"
                value={endTime}
                onChange={(event) => setEndTime(event.target.value)}
              />
            </div>
          </div>
          <p className="text-xs text-slate-500">
            Ohne Beginn/Ende ist keine Ruhezeitprüfung (§5 ArbZG) für diese Vorlage möglich – z.B. bei
            migrierten Altdaten.
          </p>

          <div className="flex flex-col gap-1.5">
            <Label>Zieltyp</Label>
            <Select value={targetPeriod} onValueChange={(value) => setTargetPeriod(value as TargetPeriod)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="DAILY">Tagessoll</SelectItem>
                <SelectItem value="WEEKLY">Wochensoll</SelectItem>
                <SelectItem value="MONTHLY">Monatssoll</SelectItem>
              </SelectContent>
            </Select>
            {targetPeriod !== 'DAILY' && (
              <p className="text-xs text-slate-500">
                Das Soll gilt für die ganze {targetPeriod === 'WEEKLY' ? 'Woche' : 'Kalendermonat'} und wird
                gleichmäßig auf die in der Standard-Schicht ausgewählten Wochentage verteilt. Nur als
                Standard-Schicht zuweisbar, nicht als einzelner Ausnahme-Tag im Kalender.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="target_minutes">
              {targetPeriod === 'DAILY'
                ? 'Soll pro Tag (Minuten)'
                : targetPeriod === 'WEEKLY'
                  ? 'Soll pro Woche (Minuten)'
                  : 'Soll pro Monat (Minuten)'}
            </Label>
            <Input
              id="target_minutes"
              type="number"
              min={0}
              step={5}
              value={targetMinutes}
              onChange={(event) => setTargetMinutes(Number(event.target.value) || 0)}
            />
          </div>

          {(targetChanged || breakChanged) && (
            <div className="flex flex-col gap-1.5 rounded-md bg-amber-50 p-3">
              <Label htmlFor="template_valid_from">{targetChanged ? 'Neues Soll gilt ab' : 'Neue Pause gilt ab'}</Label>
              <Input id="template_valid_from" type="date" value={validFrom} onChange={(e) => e.target.value && setValidFrom(e.target.value)} />
              <p className="text-xs text-amber-800">
                Tage davor rechnen weiter mit {targetChanged ? 'dem bisherigen Soll' : 'der bisherigen Pause'} (die alte
                Fassung wird archiviert).
              </p>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label>Pausenregelung</Label>
            <Select value={breakMode} onValueChange={(value) => setBreakMode(value as BreakMode)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="FLEXIBLE">Flexibel (Pause stempeln, optional feste Minuten)</SelectItem>
                <SelectItem value="FIXED">Feste Pausenzeit (wird automatisch abgezogen)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {breakMode === 'FIXED' ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="fixed_break_start">Pause von</Label>
                <Input
                  id="fixed_break_start"
                  type="time"
                  value={fixedBreakStart}
                  onChange={(event) => setFixedBreakStart(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="fixed_break_end">Pause bis</Label>
                <Input
                  id="fixed_break_end"
                  type="time"
                  value={fixedBreakEnd}
                  onChange={(event) => setFixedBreakEnd(event.target.value)}
                />
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="min_break_minutes">Feste Pause (Minuten, optional)</Label>
              <Input
                id="min_break_minutes"
                type="number"
                min={0}
                max={240}
                value={minBreakMinutes}
                onChange={(event) =>
                  setMinBreakMinutes(event.target.value === '' ? '' : Number(event.target.value))
                }
              />
            </div>
          )}
          <p className="-mt-2 text-xs text-slate-500">
            {breakMode === 'FIXED'
              ? 'Die Pausenzeit wird abgezogen, soweit der Mitarbeiter in dieser Zeit da war – auch ohne Pausenstempelung.'
              : 'Feste Minuten werden an jedem Arbeitstag mindestens abgezogen. Leer = es gelten die Pausenregeln.'}{' '}
            Die gesetzliche Pause gilt immer mindestens.
          </p>

          <div className="flex flex-col gap-1.5">
            <Label>Standort</Label>
            <Select value={locationId} onValueChange={setLocationId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_LOCATIONS}>Alle Standorte</SelectItem>
                {locations.map((location) => (
                  <SelectItem key={location.id} value={String(location.id)}>
                    {location.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
