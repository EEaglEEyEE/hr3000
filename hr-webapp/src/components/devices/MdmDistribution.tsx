import { useState } from 'react'
import { Check, Copy, KeyRound } from 'lucide-react'
import {
  useCreateEnrollmentKeyMutation,
  useDeleteEnrollmentKeyMutation,
  useEnrollmentKeysQuery,
  type CreatedEnrollmentKey,
  type EnrollmentKey,
} from '../../api/queries/devices'
import type { Location } from '../../api/queries/locations'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Label } from '../ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

function formatDate(iso: string): string {
  const withUtc = iso.endsWith('Z') ? iso : `${iso}Z`
  return new Date(withUtc).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

function KeyStatus({ entry }: { entry: EnrollmentKey | undefined }) {
  if (!entry) return <span className="text-slate-400">kein Schlüssel</span>
  if (!entry.expires_at) return <span className="text-slate-700">unbefristet</span>
  const expired = new Date(entry.expires_at.endsWith('Z') ? entry.expires_at : `${entry.expires_at}Z`) < new Date()
  return expired ? (
    <span className="font-medium text-red-600">abgelaufen am {formatDate(entry.expires_at)}</span>
  ) : (
    <span className="text-slate-700">gültig bis {formatDate(entry.expires_at)}</span>
  )
}

/** Reiter „Verteilung per MDM“: Registrierungsschlüssel je Standort erzeugen, erneuern, sperren. */
export function MdmDistribution({ locations }: { locations: Location[] }) {
  const keysQuery = useEnrollmentKeysQuery()
  const createKey = useCreateEnrollmentKeyMutation()
  const deleteKey = useDeleteEnrollmentKeyMutation()
  const [validity, setValidity] = useState('30')
  const [created, setCreated] = useState<{ result: CreatedEnrollmentKey; locationName: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const keyByLocation = new Map((keysQuery.data ?? []).map((entry) => [entry.location_id, entry]))

  async function handleCreate(location: Location) {
    setError(null)
    if (
      keyByLocation.has(location.id) &&
      !window.confirm(
        `Schlüssel für „${location.name}“ erneuern? Der bisherige gilt sofort nicht mehr – die Start-URL im MDM muss dann getauscht werden. Eingerichtete Tablets bleiben angemeldet.`,
      )
    ) {
      return
    }
    try {
      const result = await createKey.mutateAsync({
        location_id: location.id,
        valid_days: validity === 'none' ? null : Number(validity),
      })
      setCreated({ result, locationName: location.name })
    } catch {
      setError('Schlüssel konnte nicht erzeugt werden.')
    }
  }

  function handleRevoke(location: Location) {
    if (
      window.confirm(
        `Schlüssel für „${location.name}“ sperren? Neue Geräte können sich damit nicht mehr einrichten. Eingerichtete Tablets bleiben angemeldet.`,
      )
    ) {
      deleteKey.mutate(location.id)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 text-sm text-slate-600">
        <p>
          Das MDM (z. B. Intune, Endpoint Central, Jamf) startet die Kiosk-App mit einer Adresse, die den
          Registrierungsschlüssel des Standorts enthält. Neue Geräte richten sich damit selbst ein, ohne QR-Code.
        </p>
        <p>
          Ist unter „Tablets“ ein noch nie benutzter Eintrag mit demselben <strong>Gerätenamen im MDM</strong>{' '}
          angelegt, wird das Gerät direkt damit verbunden. Alle anderen Geräte warten oben auf Freigabe. Einen
          benutzten Eintrag übernimmt der Schlüssel nie.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor="enrollment_validity">Gültigkeit neuer Schlüssel</Label>
        <select
          id="enrollment_validity"
          className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
          value={validity}
          onChange={(event) => setValidity(event.target.value)}
        >
          <option value="7">7 Tage</option>
          <option value="30">30 Tage</option>
          <option value="90">90 Tage</option>
          <option value="365">1 Jahr</option>
          <option value="none">unbefristet</option>
        </select>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Standort</TableHead>
            <TableHead>Registrierungsschlüssel</TableHead>
            <TableHead>Zuletzt benutzt</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {locations.map((location) => {
            const entry = keyByLocation.get(location.id)
            return (
              <TableRow key={location.id}>
                <TableCell>{location.name}</TableCell>
                <TableCell className="text-sm">
                  <KeyStatus entry={entry} />
                </TableCell>
                <TableCell className="text-sm text-slate-500">
                  {entry?.last_used_at ? formatDate(entry.last_used_at) : '–'}
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" size="sm" disabled={createKey.isPending} onClick={() => void handleCreate(location)}>
                      <KeyRound className="h-4 w-4" />
                      {entry ? 'Erneuern' : 'Schlüssel erzeugen'}
                    </Button>
                    {entry && (
                      <Button variant="ghost" size="sm" disabled={deleteKey.isPending} onClick={() => handleRevoke(location)}>
                        Sperren
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <EnrollmentKeyDialog created={created} onClose={() => setCreated(null)} />
    </div>
  )
}

function EnrollmentKeyDialog({
  created,
  onClose,
}: {
  created: { result: CreatedEnrollmentKey; locationName: string } | null
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)
  const value = created ? (created.result.enroll_url ?? created.result.key) : ''

  return (
    <Dialog
      open={created !== null}
      onOpenChange={(open) => {
        if (!open) {
          setCopied(false)
          onClose()
        }
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Registrierungsschlüssel für „{created?.locationName}“</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 text-sm text-slate-600">
          <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-800">
            Wird nur jetzt angezeigt. Wie ein Passwort behandeln: nur im MDM hinterlegen, nicht per Mail verschicken.
          </p>
          <div className="flex flex-col gap-1.5">
            <Label>{created?.result.enroll_url ? 'Start-URL für das MDM' : 'Schlüssel'}</Label>
            <code className="break-all rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800">
              {value}
            </code>
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void navigator.clipboard?.writeText(value).then(() => setCopied(true))}
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? 'Kopiert' : 'Kopieren'}
              </Button>
            </div>
          </div>
          <p>
            Gerätenamen anhängen, damit vorbereitete Tablets ohne Freigabe zugeordnet werden:{' '}
            <code className="text-xs">&amp;name=&lt;Gerätename&gt;</code> – per Platzhalter des MDM oder unter Windows per
            Skript mit dem Computernamen. Anleitung: Handbuch für Admins, Abschnitt „Tablets per MDM verteilen“.
          </p>
        </div>
        <DialogFooter>
          <Button
            type="button"
            onClick={() => {
              setCopied(false)
              onClose()
            }}
          >
            Fertig
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
