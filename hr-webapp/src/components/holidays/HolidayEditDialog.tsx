import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { useUpdateHolidayMutation, type Holiday } from '../../api/queries/holidays'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { LocationMultiSelect } from './LocationMultiSelect'

export function HolidayEditDialog({
  holiday,
  locations,
  onOpenChange,
}: {
  holiday: Holiday | undefined
  locations: Array<{ id: number; name: string }>
  onOpenChange: (open: boolean) => void
}) {
  const updateHoliday = useUpdateHolidayMutation()
  const [date, setDate] = useState('')
  const [name, setName] = useState('')
  const [locationIds, setLocationIds] = useState<number[]>([])
  const [halfDay, setHalfDay] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (holiday) {
      setDate(holiday.date)
      setName(holiday.name)
      setLocationIds(holiday.location_ids)
      setHalfDay(holiday.half_day ?? false)
      setError(null)
    }
  }, [holiday])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!holiday) return
    setError(null)
    try {
      await updateHoliday.mutateAsync({
        holidayId: holiday.id,
        payload: { date, name, location_ids: locationIds, half_day: halfDay },
      })
      onOpenChange(false)
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'HOLIDAY_DATE_TAKEN'
          ? 'An diesem Datum gibt es für mindestens einen dieser Standorte bereits einen anderen Feiertag.'
          : 'Speichern fehlgeschlagen.',
      )
    }
  }

  return (
    <Dialog open={holiday !== undefined} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Feiertag bearbeiten</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="holiday-edit-date">Datum</Label>
            <Input
              id="holiday-edit-date"
              type="date"
              required
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="holiday-edit-name">Name</Label>
            <Input
              id="holiday-edit-name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Gilt für</Label>
            <LocationMultiSelect locations={locations} value={locationIds} onChange={setLocationIds} />
          </div>
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={halfDay} onChange={(event) => setHalfDay(event.target.checked)} />
            Halber Tag (halbes Soll, Urlaub zählt halb)
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={updateHoliday.isPending}>
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
