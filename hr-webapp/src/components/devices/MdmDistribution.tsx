import { useState } from 'react'
import { Building2, Check, Copy, KeyRound } from 'lucide-react'
import {
  useCreateEnrollmentKeyMutation,
  useDeleteCompanyEnrollmentKeyMutation,
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

/** Reiter „Verteilung per MDM“: Firmenschlüssel und Registrierungsschlüssel je Standort erzeugen, erneuern,
 * sperren. */
export function MdmDistribution({ locations }: { locations: Location[] }) {
  const keysQuery = useEnrollmentKeysQuery()
  const createKey = useCreateEnrollmentKeyMutation()
  const deleteKey = useDeleteEnrollmentKeyMutation()
  const deleteCompanyKey = useDeleteCompanyEnrollmentKeyMutation()
  const [validity, setValidity] = useState('30')
  const [created, setCreated] = useState<{ result: CreatedEnrollmentKey; title: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const keyByLocation = new Map(
    (keysQuery.data ?? []).filter((entry) => entry.location_id != null).map((entry) => [entry.location_id, entry]),
  )
  const companyKey = (keysQuery.data ?? []).find((entry) => entry.location_id == null)

  async function createFor(locationId: number | null, title: string) {
    setError(null)
    try {
      const result = await createKey.mutateAsync({
        location_id: locationId,
        valid_days: validity === 'none' ? null : Number(validity),
      })
      setCreated({ result, title })
    } catch {
      setError('Schlüssel konnte nicht erzeugt werden.')
    }
  }

  function handleCreateCompany() {
    if (
      companyKey &&
      !window.confirm(
        'Firmenschlüssel erneuern? Der bisherige gilt sofort nicht mehr – im MDM muss er dann getauscht werden. Eingerichtete Tablets bleiben angemeldet.',
      )
    ) {
      return
    }
    void createFor(null, 'Firmenschlüssel (alle Standorte)')
  }

  function handleRevokeCompany() {
    if (
      window.confirm(
        'Firmenschlüssel sperren? Neue Geräte können sich damit nicht mehr einrichten. Eingerichtete Tablets bleiben angemeldet.',
      )
    ) {
      deleteCompanyKey.mutate()
    }
  }

  function handleCreate(location: Location) {
    if (
      keyByLocation.has(location.id) &&
      !window.confirm(
        `Schlüssel für „${location.name}“ erneuern? Der bisherige gilt sofort nicht mehr – die Start-URL im MDM muss dann getauscht werden. Eingerichtete Tablets bleiben angemeldet.`,
      )
    ) {
      return
    }
    void createFor(location.id, `Registrierungsschlüssel für „${location.name}“`)
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
      <section aria-label="Firmenschlüssel" className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 max-w-2xl">
            <h3 className="flex items-center gap-2 font-medium text-slate-900">
              <Building2 className="h-4 w-4 text-slate-500" />
              Firmenschlüssel (alle Standorte)
            </h3>
            <p className="mt-1 text-sm text-slate-600">
              Ein Schlüssel für alle Tablets – gedacht für die Android-App „HR3000 Kiosk“ und für MDMs, die eine
              App-Konfiguration nur je App setzen (z. B. Endpoint Central). Neue Geräte warten auf Freigabe, den Standort
              wählst du dabei. Ein schon eingerichtetes Tablet oder ein vorbereiteter Eintrag mit gleichem Gerätenamen
              wird an jedem Standort wiedererkannt.
            </p>
            <p className="mt-2 text-sm">
              <KeyStatus entry={companyKey} />
              {companyKey?.last_used_at && (
                <span className="text-slate-500"> · zuletzt benutzt {formatDate(companyKey.last_used_at)}</span>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={createKey.isPending} onClick={handleCreateCompany}>
              <KeyRound className="h-4 w-4" />
              {companyKey ? 'Erneuern' : 'Schlüssel erzeugen'}
            </Button>
            {companyKey && (
              <Button variant="ghost" size="sm" disabled={deleteCompanyKey.isPending} onClick={handleRevokeCompany}>
                Sperren
              </Button>
            )}
          </div>
        </div>
      </section>
      <h3 className="font-medium text-slate-900">Schlüssel je Standort</h3>
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
                    <Button variant="outline" size="sm" disabled={createKey.isPending} onClick={() => handleCreate(location)}>
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

function CopyField({ label, value, hint }: { label: string; value: string; hint?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex flex-col gap-1">
      <Label>{label}</Label>
      <div className="flex items-start gap-2">
        <code className="min-w-0 flex-1 break-all rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800">
          {value}
        </code>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={`${label} kopieren`}
          onClick={() => void navigator.clipboard?.writeText(value).then(() => setCopied(true))}
        >
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copied ? 'Kopiert' : 'Kopieren'}
        </Button>
      </div>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

function EnrollmentKeyDialog({
  created,
  onClose,
}: {
  created: { result: CreatedEnrollmentKey; title: string } | null
  onClose: () => void
}) {
  const result = created?.result
  return (
    <Dialog open={created !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{created?.title}</DialogTitle>
        </DialogHeader>
        {result && (
          <div className="flex flex-col gap-4 text-sm text-slate-600">
            <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-800">
              Wird nur jetzt angezeigt. Wie ein Passwort behandeln: nur im MDM hinterlegen, nicht per Mail verschicken.
            </p>
            <section aria-label="Android-App" className="flex flex-col gap-3">
              <h4 className="font-medium text-slate-900">Android-App „HR3000 Kiosk“ – App-Konfiguration im MDM</h4>
              {result.kiosk_url && <CopyField label="Kiosk-Adresse (kiosk_url)" value={result.kiosk_url} />}
              <CopyField label="Registrierungsschlüssel (enrollment_key)" value={result.key} />
              <CopyField
                label="Gerätename (device_name, optional)"
                value="%devicename%"
                hint="Platzhalter von Endpoint Central für den Gerätenamen; in anderen MDMs deren Platzhalter."
              />
            </section>
            {result.enroll_url && (
              <section aria-label="Web-App" className="flex flex-col gap-2 border-t border-slate-200 pt-3">
                <h4 className="font-medium text-slate-900">Web-App oder Browser – Start-URL</h4>
                <CopyField
                  label="Start-URL"
                  value={result.enroll_url}
                  hint="Gerätenamen anhängen, damit vorbereitete Tablets ohne Freigabe zugeordnet werden: &name=<Gerätename> – per Platzhalter des MDM oder unter Windows per Skript mit dem Computernamen."
                />
              </section>
            )}
            <p>Anleitung: Handbuch für Admins, Abschnitt „Tablets per MDM verteilen“.</p>
          </div>
        )}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Fertig
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
