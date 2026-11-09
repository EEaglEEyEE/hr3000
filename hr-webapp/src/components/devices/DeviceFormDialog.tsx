import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
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
  // Gerätename im MDM: Meldet sich ein Gerät mit diesem Namen per Registrierungsschlüssel, wird es ohne Freigabe verbunden
  const [mdmName, setMdmName] = useState('')
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
    setMdmName(device?.mdm_name ?? '')
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
            mdm_name: mdmName.trim(),
            theme,
            screen_hours_mode: screenMode,
            ...(screenMode === 'CUSTOM' ? { screen_on_from: screenFrom, screen_on_until: screenUntil } : {}),
          },
        })
      } else {
        await createDevice.mutateAsync({ name, location_id: Number(locationId), mdm_name: mdmName.trim() || null })
      }
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError && err.code === 'MDM_NAME_TAKEN' ? err.message : 'Speichern fehlgeschlagen.')
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
              placeholder="z. B. Tablet Eingang"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="device_mdm_name">Gerätename im MDM (optional)</Label>
            <Input
              id="device_mdm_name"
              placeholder="z. B. NB-FRA-01"
              maxLength={100}
              value={mdmName}
              onChange={(event) => setMdmName(event.target.value)}
            />
            <p className="text-xs text-slate-500">
              Für die Verteilung per MDM: Meldet sich ein Gerät mit diesem Namen per Registrierungsschlüssel, wird es
              ohne Freigabe mit diesem Eintrag verbunden – nur solange der Eintrag noch nie benutzt wurde.
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Standort</Label>
            {/* Leere Werte ignorieren: Radix meldet beim Vorbelegen sonst kurz '' (siehe docs/technik.md) */}
            <Select value={locationId} onValueChange={(value) => value && setLocationId(value)}>
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
                  <SelectItem value="DEFAULT">Standard (Einstellungen → „Anzeige am Tablet“)</SelectItem>
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
                <option value="DEFAULT">Wie Einstellungen („Anzeige am Tablet“)</option>
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
              Kopplung aufheben (z. B. bei Verlust des Tablets) – danach mit dem QR-Code neu koppeln
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
