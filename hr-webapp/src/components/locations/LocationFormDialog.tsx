import { useEffect, useState, type FormEvent } from 'react'
import {
  useCreateLocationMutation,
  useUpdateLocationMutation,
  type Bundesland,
  type Location,
} from '../../api/queries/locations'
import { ApiError } from '../../api/client'
import { currentPosition, parseGeofence } from '../../lib/geolocation'
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

/** Zeitzonen zur Auswahl (Browser-Liste, sonst die üblichen in Europa). Das Backend prüft streng. */
const TIMEZONES: string[] = (() => {
  try {
    const all = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone')
    if (all && all.length > 0) return all
  } catch {
    // ältere Browser
  }
  return ['Europe/Berlin', 'Europe/Vienna', 'Europe/Zurich', 'Europe/Amsterdam', 'Europe/Paris', 'Europe/London', 'Europe/Warsaw', 'Europe/Prague']
})()

export function LocationFormDialog({ open, onOpenChange, location }: LocationFormDialogProps) {
  const isEditMode = location !== undefined
  const createLocation = useCreateLocationMutation()
  const updateLocation = useUpdateLocationMutation()

  const [name, setName] = useState('')
  const [timezone, setTimezone] = useState('Europe/Berlin')
  const [bundesland, setBundesland] = useState(NO_BUNDESLAND)
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [radius, setRadius] = useState('')
  const [locating, setLocating] = useState(false)
  const [locateInfo, setLocateInfo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(location?.name ?? '')
    setTimezone(location?.timezone ?? 'Europe/Berlin')
    setBundesland(location?.bundesland ?? NO_BUNDESLAND)
    setLatitude(location?.geo_latitude != null ? String(location.geo_latitude) : '')
    setLongitude(location?.geo_longitude != null ? String(location.geo_longitude) : '')
    setRadius(location?.geo_radius_m != null ? String(location.geo_radius_m) : '')
    setLocateInfo(null)
    setError(null)
  }, [open, location])

  /** Hilfe beim Einrichten: Position dieses Geräts als Mittelpunkt übernehmen (nur auf Knopfdruck). */
  async function takeCurrentPosition() {
    setLocating(true)
    setLocateInfo(null)
    const position = await currentPosition()
    setLocating(false)
    if (!position) {
      setLocateInfo('Der Standort konnte nicht ermittelt werden – Freigabe im Browser erlauben oder Koordinaten eintragen.')
      return
    }
    setLatitude(position.latitude.toFixed(6))
    setLongitude(position.longitude.toFixed(6))
    if (radius.trim() === '') setRadius('200')
    setLocateInfo(`Übernommen (Genauigkeit ca. ${Math.round(position.accuracy_m)} m).`)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const selectedBundesland = bundesland === NO_BUNDESLAND ? undefined : (bundesland as Bundesland)
    const geofence = parseGeofence(latitude, longitude, radius)
    if (typeof geofence === 'string') {
      setError(geofence)
      return
    }
    try {
      if (isEditMode) {
        await updateLocation.mutateAsync({
          locationId: location.id,
          payload: {
            name,
            timezone,
            bundesland: selectedBundesland,
            clear_bundesland: selectedBundesland === undefined,
            ...(geofence ? { ...geofence, clear_geofence: false } : { clear_geofence: location.geo_radius_m != null }),
          },
        })
      } else {
        await createLocation.mutateAsync({ name, timezone, bundesland: selectedBundesland, ...(geofence ?? {}) })
      }
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen.')
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
              list="location_timezones"
              placeholder="z.B. Europe/Berlin"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
            />
            <datalist id="location_timezones">
              {TIMEZONES.map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
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
              werden (siehe Einstellungen → „Feiertagskalender“).
            </p>
          </div>
          <div role="group" aria-label="Kreis für die Standortprüfung beim Stempeln" className="flex flex-col gap-2 rounded-md border border-slate-200 p-3">
            <p className="text-sm font-medium text-slate-800">Kreis für die Standortprüfung beim Stempeln</p>
            <p className="text-xs text-slate-500">
              Optional. Mittelpunkt als Breite/Länge in Grad (z. B. aus einem Kartendienst kopiert) und Radius in Metern. Wird
              nur genutzt, wenn unter Einstellungen → „Stempeln“ die Standortprüfung eingeschaltet ist. Alle drei Felder leer
              = kein Kreis.
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor="location_geo_latitude">Breite</Label>
                <Input id="location_geo_latitude" inputMode="decimal" placeholder="z.B. 48.775800" value={latitude}
                  onChange={(event) => setLatitude(event.target.value)} />
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor="location_geo_longitude">Länge</Label>
                <Input id="location_geo_longitude" inputMode="decimal" placeholder="z.B. 9.182900" value={longitude}
                  onChange={(event) => setLongitude(event.target.value)} />
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor="location_geo_radius">Radius (m)</Label>
                <Input id="location_geo_radius" inputMode="numeric" placeholder="50–5000" value={radius}
                  onChange={(event) => setRadius(event.target.value)} />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="outline" size="sm" className="h-auto min-h-8 whitespace-normal py-1.5"
                disabled={locating} onClick={() => void takeCurrentPosition()}>
                {locating ? 'Standort wird ermittelt…' : 'Aktuellen Standort übernehmen'}
              </Button>
              {(latitude || longitude || radius) && (
                <Button type="button" variant="ghost" size="sm"
                  onClick={() => { setLatitude(''); setLongitude(''); setRadius(''); setLocateInfo(null) }}>
                  Kreis entfernen
                </Button>
              )}
            </div>
            {locateInfo && <p className="text-xs text-slate-500">{locateInfo}</p>}
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
