import { useEffect, useState, type FormEvent } from 'react'
import { useCreateDeviceMutation, useUpdateDeviceMutation, type Device } from '../../api/queries/devices'
import type { Location } from '../../api/queries/locations'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface DeviceFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  device?: Device
  locations: Location[]
}

export function DeviceFormDialog({ open, onOpenChange, device, locations }: DeviceFormDialogProps) {
  const isEditMode = device !== undefined
  const createDevice = useCreateDeviceMutation()
  const updateDevice = useUpdateDeviceMutation()

  const [name, setName] = useState('')
  const [locationId, setLocationId] = useState('')
  const [regenerateToken, setRegenerateToken] = useState(false)
  const [theme, setTheme] = useState<'DEFAULT' | 'DARK' | 'LIGHT'>('DEFAULT')
  // Bildschirmzeiten dieses Tablets: wie Einstellungen / immer an / eigene Zeiten
  const [screenMode, setScreenMode] = useState<'DEFAULT' | 'ALWAYS' | 'CUSTOM'>('DEFAULT')
  const [screenFrom, setScreenFrom] = useState('06:00')
  const [screenUntil, setScreenUntil] = useState('21:00')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(device?.name ?? '')
    setLocationId(device ? String(device.location_id) : locations[0] ? String(locations[0].id) : '')
    setRegenerateToken(false)
    setTheme(device?.theme === 'DARK' || device?.theme === 'LIGHT' ? device.theme : 'DEFAULT')
    setScreenMode(device?.screen_hours_mode === 'ALWAYS' || device?.screen_hours_mode === 'CUSTOM' ? device.screen_hours_mode : 'DEFAULT')
    setScreenFrom(device?.screen_on_from?.slice(0, 5) ?? '06:00')
    setScreenUntil(device?.screen_on_until?.slice(0, 5) ?? '21:00')
    setError(null)
  }, [open, device, locations])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (isEditMode && screenMode === 'CUSTOM' && (!screenFrom || !screenUntil || screenFrom === screenUntil)) {
      setError('Bitte für die Bildschirmzeiten „von“ und „bis“ angeben (nicht gleich).')
      return
    }
    try {
      if (isEditMode) {
        await updateDevice.mutateAsync({
          deviceId: device.id,
          payload: {
            name,
            location_id: Number(locationId),
            regenerate_token: regenerateToken,
            theme,
            screen_hours_mode: screenMode,
            ...(screenMode === 'CUSTOM' ? { screen_on_from: screenFrom, screen_on_until: screenUntil } : {}),
          },
        })
      } else {
        await createDevice.mutateAsync({ name, location_id: Number(locationId) })
      }
      onOpenChange(false)
    } catch {
      setError('Speichern fehlgeschlagen.')
    }
  }

  const isSubmitting = createDevice.isPending || updateDevice.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Tablet bearbeiten' : 'Neues Tablet'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="device_name">Name</Label>
            <Input
              id="device_name"
              required
              placeholder="z.B. Kiosk Eingang"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Standort</Label>
            <Select value={locationId} onValueChange={setLocationId}>
              <SelectTrigger>
                <SelectValue placeholder="Standort wählen" />
              </SelectTrigger>
              <SelectContent>
                {locations.map((location) => (
                  <SelectItem key={location.id} value={String(location.id)}>
                    {location.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {isEditMode && (
            <div className="flex flex-col gap-1.5">
              <Label>Darstellung</Label>
              <Select value={theme} onValueChange={(value) => setTheme(value as typeof theme)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="DEFAULT">Standard (Einstellungen → Kiosk)</SelectItem>
                  <SelectItem value="DARK">Dunkel</SelectItem>
                  <SelectItem value="LIGHT">Hell</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          {isEditMode && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="device_screen_mode">Bildschirmzeiten</Label>
              <select
                id="device_screen_mode"
                className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
                value={screenMode}
                onChange={(event) => setScreenMode(event.target.value as typeof screenMode)}
              >
                <option value="DEFAULT">Wie Einstellungen (Einstellungen → Kiosk)</option>
                <option value="ALWAYS">Immer an</option>
                <option value="CUSTOM">Eigene Zeiten</option>
              </select>
              {screenMode === 'CUSTOM' && (
                <div className="flex items-center gap-2">
                  <Input
                    type="time"
                    aria-label="Bildschirm an von"
                    required
                    className="w-28"
                    value={screenFrom}
                    onChange={(event) => setScreenFrom(event.target.value)}
                  />
                  <span className="text-sm text-slate-500">bis</span>
                  <Input
                    type="time"
                    aria-label="Bildschirm an bis"
                    required
                    className="w-28"
                    value={screenUntil}
                    onChange={(event) => setScreenUntil(event.target.value)}
                  />
                </div>
              )}
            </div>
          )}
          {isEditMode && (
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={regenerateToken}
                onChange={(event) => setRegenerateToken(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              Token neu generieren (z.B. bei Verlust des Tablets)
            </label>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isSubmitting || !locationId}>
              {isSubmitting ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
