import { useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import {
  useApproveEnrollmentMutation,
  useEnrollmentsQuery,
  useRejectEnrollmentMutation,
  type Device,
  type DeviceEnrollment,
} from '../../api/queries/devices'
import type { Location } from '../../api/queries/locations'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

function formatDateTime(iso: string): string {
  const withUtc = iso.endsWith('Z') ? iso : `${iso}Z`
  return new Date(withUtc).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

/** Geräte, die sich per Registrierungsschlüssel (MDM) gemeldet haben und auf Freigabe warten. */
export function PendingEnrollments({ locations, devices }: { locations: Location[]; devices: Device[] }) {
  const enrollmentsQuery = useEnrollmentsQuery()
  const reject = useRejectEnrollmentMutation()
  const [approving, setApproving] = useState<DeviceEnrollment | undefined>(undefined)
  const items = enrollmentsQuery.data ?? []
  if (items.length === 0) return null
  const locationName = new Map(locations.map((location) => [location.id, location.name]))

  function handleReject(item: DeviceEnrollment) {
    if (
      window.confirm(
        `Anfrage von „${item.reported_name ?? 'Gerät ohne Namen'}“ ablehnen? Startet das Gerät neu, meldet es sich erneut – dauerhaft hilft nur, es im MDM zu entfernen oder den Schlüssel zu erneuern.`,
      )
    ) {
      reject.mutate(item.id)
    }
  }

  return (
    <section aria-label="Neue Geräte" className="rounded-lg border border-amber-200 bg-amber-50 p-4">
      <h2 className="text-base font-semibold text-amber-900">Neue Geräte warten auf Freigabe ({items.length})</h2>
      <p className="mt-1 text-sm text-amber-800">
        Vor dem Freigeben den Prüfcode mit dem Code auf dem Bildschirm des Geräts vergleichen.
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {items.map((item) => (
          <li
            key={item.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-200 bg-white p-3"
          >
            <div className="min-w-0">
              <p className="font-medium text-slate-900">
                {item.reported_name ?? 'Gerät ohne Namen'}
                <span className="ml-2 font-mono text-sm font-normal text-slate-600">Prüfcode {item.verify_code}</span>
              </p>
              <p className="text-xs text-slate-500">
                Standort {locationName.get(item.location_id) ?? '–'} · gemeldet {formatDateTime(item.created_at)}
              </p>
              {item.conflict_device_name && (
                <p className="mt-1 text-xs font-medium text-red-600">
                  Achtung: Das Tablet „{item.conflict_device_name}“ mit diesem Gerätenamen ist bereits in Benutzung. Nur
                  freigeben, wenn das Gerät wirklich ersetzt wurde.
                </p>
              )}
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => setApproving(item)}>
                Freigeben
              </Button>
              <Button size="sm" variant="outline" disabled={reject.isPending} onClick={() => handleReject(item)}>
                Ablehnen
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <Dialog open={approving !== undefined} onOpenChange={(open) => !open && setApproving(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Gerät freigeben</DialogTitle>
          </DialogHeader>
          {approving && (
            <ApproveForm
              key={approving.id}
              enrollment={approving}
              devices={devices.filter((device) => device.location_id === approving.location_id)}
              onDone={() => setApproving(undefined)}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}

function ApproveForm({
  enrollment,
  devices,
  onDone,
}: {
  enrollment: DeviceEnrollment
  devices: Device[]
  onDone: () => void
}) {
  const approve = useApproveEnrollmentMutation()
  const [mode, setMode] = useState<'new' | 'replace'>('new')
  const [name, setName] = useState(enrollment.reported_name ?? '')
  const [deviceId, setDeviceId] = useState(devices[0] ? String(devices[0].id) : '')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      await approve.mutateAsync({
        enrollmentId: enrollment.id,
        payload: mode === 'replace' ? { device_id: Number(deviceId) } : { name: name.trim() || null },
      })
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Freigeben fehlgeschlagen.')
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
      <p className="text-sm text-slate-600">
        Gerät „{enrollment.reported_name ?? 'ohne Namen'}“, Prüfcode{' '}
        <span className="font-mono font-medium text-slate-900">{enrollment.verify_code}</span>. Nach dem Freigeben meldet
        es sich innerhalb einer Minute von selbst an.
      </p>
      <fieldset className="flex flex-col gap-2">
        <legend className="sr-only">Freigeben als</legend>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="radio" name="approve_mode" checked={mode === 'new'} onChange={() => setMode('new')} />
          Als neues Tablet anlegen
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="radio"
            name="approve_mode"
            checked={mode === 'replace'}
            disabled={devices.length === 0}
            onChange={() => setMode('replace')}
          />
          Vorhandenes Tablet ersetzen (das bisherige Gerät wird abgemeldet)
        </label>
      </fieldset>
      {mode === 'new' ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="enrollment_name">Name des Tablets</Label>
          <Input
            id="enrollment_name"
            placeholder="z. B. Tablet Eingang"
            maxLength={255}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="enrollment_device">Tablet</Label>
          <select
            id="enrollment_device"
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={deviceId}
            onChange={(event) => setDeviceId(event.target.value)}
          >
            {devices.map((device) => (
              <option key={device.id} value={String(device.id)}>
                {device.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Abbrechen
        </Button>
        <Button type="submit" disabled={approve.isPending || (mode === 'replace' && !deviceId)}>
          Freigeben
        </Button>
      </DialogFooter>
    </form>
  )
}
