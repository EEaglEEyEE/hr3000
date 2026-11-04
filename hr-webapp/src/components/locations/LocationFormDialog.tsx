import { useEffect, useState, type FormEvent } from 'react'
import {
  useCreateLocationMutation,
  useUpdateLocationMutation,
  type Bundesland,
  type Location,
} from '../../api/queries/locations'
import { BUNDESLAND_LABELS } from '../../lib/labels'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface LocationFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  location?: Location
}

const NO_BUNDESLAND = '__none__'

export function LocationFormDialog({ open, onOpenChange, location }: LocationFormDialogProps) {
  const isEditMode = location !== undefined
  const createLocation = useCreateLocationMutation()
  const updateLocation = useUpdateLocationMutation()

  const [name, setName] = useState('')
  const [timezone, setTimezone] = useState('Europe/Berlin')
  const [bundesland, setBundesland] = useState(NO_BUNDESLAND)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(location?.name ?? '')
    setTimezone(location?.timezone ?? 'Europe/Berlin')
    setBundesland(location?.bundesland ?? NO_BUNDESLAND)
    setError(null)
  }, [open, location])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const selectedBundesland = bundesland === NO_BUNDESLAND ? undefined : (bundesland as Bundesland)
    try {
      if (isEditMode) {
        await updateLocation.mutateAsync({
          locationId: location.id,
          payload: {
            name,
            timezone,
            bundesland: selectedBundesland,
            clear_bundesland: selectedBundesland === undefined,
          },
        })
      } else {
        await createLocation.mutateAsync({ name, timezone, bundesland: selectedBundesland })
      }
      onOpenChange(false)
    } catch {
      setError('Speichern fehlgeschlagen.')
    }
  }

  const isSubmitting = createLocation.isPending || updateLocation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Standort bearbeiten' : 'Neuer Standort'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="location_name">Name</Label>
            <Input
              id="location_name"
              required
              placeholder="z.B. Standort A"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="location_timezone">Zeitzone</Label>
            <Input
              id="location_timezone"
              required
              placeholder="z.B. Europe/Berlin"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Bundesland</Label>
            <Select value={bundesland} onValueChange={setBundesland}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_BUNDESLAND}>Kein eigenes (Standard-Bundesland verwenden)</SelectItem>
                {Object.entries(BUNDESLAND_LABELS).map(([code, label]) => (
                  <SelectItem key={code} value={code}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-slate-500">
              Bestimmt, welche Feiertage automatisch für Mitarbeiter dieses Standorts importiert
              werden (siehe Feiertage-Seite).
            </p>
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
