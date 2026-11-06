import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { useAbsenceTypesQuery } from '../../api/queries/absenceTypes'
import { useCreateAbsenceMutation, useUpdateAbsenceMutation, type Absence } from '../../api/queries/absences'
import { todayIsoDate } from '../../lib/format'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface AbsenceFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  employeeId: number
  absence?: Absence
  /** Mitarbeiter stellt selbst einen Antrag: nur dafür freigegebene Arten. */
  selfService?: boolean
}

export function AbsenceFormDialog({ open, onOpenChange, employeeId, absence, selfService = false }: AbsenceFormDialogProps) {
  const isEditMode = absence !== undefined
  const createAbsence = useCreateAbsenceMutation(employeeId)
  const updateAbsence = useUpdateAbsenceMutation(employeeId)

  const typesQuery = useAbsenceTypesQuery()
  const types = (typesQuery.data ?? []).filter(
    (t) => (t.active && (!selfService || t.employee_can_request)) || t.id === absence?.absence_type_id,
  )
  const [typeId, setTypeId] = useState('')
  const [dateFrom, setDateFrom] = useState(todayIsoDate())
  const [dateTo, setDateTo] = useState(todayIsoDate())
  const [note, setNote] = useState('')
  // Umfang: ganzer Tag, halber Tag oder genaue Stunden (z.B. 3 Std. Homeoffice)
  const [scope, setScope] = useState<'FULL' | 'HALF' | 'HOURS'>('FULL')
  const [hours, setHours] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setTypeId(absence?.absence_type_id ? String(absence.absence_type_id) : '')
    setDateFrom(absence?.date_from ?? todayIsoDate())
    setDateTo(absence?.date_to ?? todayIsoDate())
    setNote(absence?.note ?? '')
    setScope(absence?.duration_minutes != null ? 'HOURS' : absence?.half_day ? 'HALF' : 'FULL')
    setHours(absence?.duration_minutes != null ? String(absence.duration_minutes / 60).replace('.', ',') : '')
    setError(null)
  }, [open, absence])

  // Ohne Auswahl die erste passende Art (in der Regel "Urlaub") vorbelegen.
  const effectiveTypeId =
    typeId || String(types.find((t) => t.category === (absence?.type ?? 'VACATION'))?.id ?? types[0]?.id ?? '')
  const selectedType = types.find((t) => String(t.id) === effectiveTypeId)
  // Halber Tag und Stunden gehen nur für einen einzelnen Tag (z.B. ½ Urlaub, an Heiligabend
  // ½ Sonderurlaub + ½ Urlaub, oder 3 Std. Homeoffice). Urlaub zählt in Tagen, nie in Stunden.
  const singleDay = dateFrom === dateTo
  const hoursAllowed = selectedType?.category !== 'VACATION'
  const effectiveScope = !singleDay ? 'FULL' : scope === 'HOURS' && !hoursAllowed ? 'FULL' : scope
  const durationMinutes = Math.round(Number(hours.replace(',', '.')) * 60)
  const hoursValid = durationMinutes >= 1 && durationMinutes <= 960

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    await save(false)
  }

  /** splitVacation: Krankheit im Urlaub – Urlaubstage zurückgeben (§ 9 BUrlG), nach Rückfrage. */
  async function save(splitVacation: boolean) {
    try {
      if (isEditMode) {
        await updateAbsence.mutateAsync({
          absenceId: absence.id,
          payload: {
            absence_type_id: Number(effectiveTypeId),
            date_from: dateFrom,
            date_to: dateTo,
            half_day: effectiveScope === 'HALF',
            duration_minutes: effectiveScope === 'HOURS' ? durationMinutes : undefined,
            clear_duration: effectiveScope !== 'HOURS',
            note: note || null,
            split_vacation: splitVacation,
          },
        })
      } else {
        await createAbsence.mutateAsync({
          employee_id: employeeId,
          absence_type_id: Number(effectiveTypeId),
          date_from: dateFrom,
          date_to: dateTo,
          half_day: effectiveScope === 'HALF',
          ...(effectiveScope === 'HOURS' ? { duration_minutes: durationMinutes } : {}),
          note: note || undefined,
          split_vacation: splitVacation,
        })
      }
      onOpenChange(false)
    } catch (err) {
      if (
        !splitVacation &&
        err instanceof ApiError &&
        err.code === 'ABSENCE_OVERLAP_VACATION' &&
        window.confirm(`${err.message}\n\nUrlaubstage für die Krankheitstage zurückgeben?`)
      ) {
        await save(true)
        return
      }
      setError(
        err instanceof ApiError && err.status !== 422
          ? err.message
          : "'Bis' darf nicht vor 'Von' liegen, oder Speichern ist fehlgeschlagen.",
      )
    }
  }

  const isSubmitting = createAbsence.isPending || updateAbsence.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Abwesenheit bearbeiten' : 'Neue Abwesenheit'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label>Art</Label>
            <Select value={effectiveTypeId} onValueChange={setTypeId}>
              <SelectTrigger>
                <SelectValue placeholder="Art wählen" />
              </SelectTrigger>
              <SelectContent>
                {types.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>
                    <span className="inline-flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: t.color }} />
                      {t.name}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selfService && selectedType?.requires_approval && (
              <p className="text-xs text-slate-500">Wird erst nach Genehmigung wirksam.</p>
            )}
            {selectedType?.certificate_from_day && (
              <p className="text-xs text-slate-500">
                Nachweis (z. B. AU-Bescheinigung) ab dem {selectedType.certificate_from_day}. Tag erforderlich.
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="date_from">Von</Label>
              <Input
                id="date_from"
                type="date"
                required
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="date_to">Bis</Label>
              <Input
                id="date_to"
                type="date"
                required
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
              />
            </div>
          </div>
          {singleDay && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="absence_scope">Umfang</Label>
              <select
                id="absence_scope"
                className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
                value={effectiveScope}
                onChange={(event) => setScope(event.target.value as 'FULL' | 'HALF' | 'HOURS')}
              >
                <option value="FULL">Ganzer Tag</option>
                <option value="HALF">Halber Tag</option>
                {hoursAllowed && <option value="HOURS">Stunden</option>}
              </select>
              {effectiveScope === 'HALF' && (
                <p className="text-xs text-slate-500">
                  Zählt als ½ Tag (bei Urlaub ½ Urlaubstag); die andere Hälfte wird normal gearbeitet oder mit einer
                  zweiten halben Abwesenheit belegt.
                </p>
              )}
              {effectiveScope === 'HOURS' && (
                <>
                  <div className="flex items-center gap-2">
                    <Input
                      id="absence_hours"
                      aria-label="Stunden"
                      inputMode="decimal"
                      required
                      className="w-24"
                      placeholder="z. B. 3"
                      value={hours}
                      onChange={(event) => setHours(event.target.value)}
                    />
                    <span className="text-sm text-slate-500">Stunden (z. B. 1, 3 oder 1,5)</span>
                  </div>
                  <p className="text-xs text-slate-500">
                    Genau diese Zeit wird gutgeschrieben (unbezahlt: das Soll sinkt um diese Zeit). Zusätzlich
                    gestempelte Arbeit zählt dazu.
                  </p>
                </>
              )}
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="note">Notiz (optional)</Label>
            <Input id="note" value={note} onChange={(event) => setNote(event.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isSubmitting || !effectiveTypeId || (effectiveScope === 'HOURS' && !hoursValid)}>
              {isSubmitting ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
