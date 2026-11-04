import { useEffect, useState, type FormEvent } from 'react'
import { useCreateTeamMutation, useUpdateTeamMutation, type Team } from '../../api/queries/teams'
import type { Location } from '../../api/queries/locations'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface TeamFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  team?: Team
  locations: Location[]
}

const NO_LOCATION = '__none__'

export function TeamFormDialog({ open, onOpenChange, team, locations }: TeamFormDialogProps) {
  const isEditMode = team !== undefined
  const createTeam = useCreateTeamMutation()
  const updateTeam = useUpdateTeamMutation()

  const [name, setName] = useState('')
  const [locationId, setLocationId] = useState(NO_LOCATION)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(team?.name ?? '')
    setLocationId(team?.location_id ? String(team.location_id) : NO_LOCATION)
    setError(null)
  }, [open, team])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const selectedLocationId = locationId === NO_LOCATION ? undefined : Number(locationId)
    try {
      if (isEditMode) {
        await updateTeam.mutateAsync({
          teamId: team.id,
          payload: {
            name,
            location_id: selectedLocationId,
            clear_location_id: selectedLocationId === undefined,
          },
        })
      } else {
        await createTeam.mutateAsync({ name, location_id: selectedLocationId })
      }
      onOpenChange(false)
    } catch {
      setError('Speichern fehlgeschlagen.')
    }
  }

  const isSubmitting = createTeam.isPending || updateTeam.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Team bearbeiten' : 'Neues Team'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="team_name">Name</Label>
            <Input
              id="team_name"
              required
              placeholder="z.B. Team Nord"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Standort (optional)</Label>
            <Select value={locationId} onValueChange={setLocationId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_LOCATION}>Kein Standort (standortübergreifend)</SelectItem>
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
