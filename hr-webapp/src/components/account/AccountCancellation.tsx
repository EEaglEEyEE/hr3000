import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { useCancelAccountMutation, useRevokeCancellationMutation } from '../../api/queries/account'
import { usePlanQuery } from '../../api/queries/plan'
import { useAuth } from '../../auth/AuthContext'
import { formatDate } from '../../lib/format'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

/** Adresse der Firma, wie sie zur Bestätigung eingetippt wird (erster Teil des Hostnamens). */
export function currentSubdomain(): string {
  return window.location.hostname.split('.')[0]
}

/** Einstellungen → „Tarif & Konto“: HR3000 kündigen bzw. Kündigung zurücknehmen (nur Admins). */
export function AccountCancellationCard() {
  const plan = usePlanQuery().data
  const cancel = useCancelAccountMutation()
  const revoke = useRevokeCancellationMutation()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState('')
  const subdomain = currentSubdomain()

  useEffect(() => {
    if (open) {
      setConfirm('')
      cancel.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!plan) return null
  const cancelled = plan.deletion_due_on != null

  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div>
        <p className="text-sm font-medium text-slate-800">Konto kündigen</p>
        {cancelled ? (
          <p className="text-sm text-amber-800">
            Gekündigt zum {formatDate(plan.contract_end ?? '')}. Bis zum {formatDate(plan.deletion_due_on ?? '')} könnt
            ihr HR3000 weiter nutzen und alles exportieren (Analysen, Lohn-Export, DSGVO-Datenexport je
            Mitarbeiter) – danach werden alle Daten endgültig gelöscht.
          </p>
        ) : (
          <p className="text-sm text-slate-500">
            Kündigung jederzeit zum Monatsende. Danach habt ihr noch 30 Tage Zeit, eure Daten zu exportieren; dann
            werden sie endgültig gelöscht. Bis dahin lässt sich die Kündigung zurücknehmen.
          </p>
        )}
      </div>
      {revoke.isError && <p className="text-sm text-red-600">Das hat nicht geklappt.</p>}
      <div>
        {cancelled ? (
          <Button type="button" variant="outline" disabled={revoke.isPending} onClick={() => revoke.mutate()}>
            Kündigung zurücknehmen
          </Button>
        ) : (
          <Button type="button" variant="outline" onClick={() => setOpen(true)}>
            HR3000 kündigen…
          </Button>
        )}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>HR3000 kündigen</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3 text-sm text-slate-700">
            <p>
              Die Kündigung gilt zum Ende dieses Monats. Danach könnt ihr HR3000 noch 30 Tage nutzen und alle Daten
              exportieren. Anschließend werden <strong>alle Daten eurer Firma endgültig gelöscht</strong> – Mitarbeiter,
              Zeiten, Abwesenheiten, Dokumente. Bis dahin lässt sich die Kündigung hier zurücknehmen.
            </p>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cancel-confirm">
                Zur Bestätigung die Adresse eurer Firma eingeben: <span className="font-mono">{subdomain}</span>
              </Label>
              <Input
                id="cancel-confirm"
                autoComplete="off"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>
            {cancel.isError && (
              <p className="text-red-600">{cancel.error instanceof ApiError ? cancel.error.message : 'Das hat nicht geklappt.'}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Abbrechen
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={cancel.isPending || confirm.trim().toLowerCase() !== subdomain}
              onClick={() => cancel.mutate(confirm.trim(), { onSuccess: () => setOpen(false) })}
            >
              Verbindlich kündigen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** Hinweis oben in der HR-Ansicht, solange eine Kündigung läuft. */
export function CancellationBanner() {
  const { hasHrAccess, isSuperAdmin, isAdmin } = useAuth()
  const plan = usePlanQuery(hasHrAccess && !isSuperAdmin).data
  if (!plan?.deletion_due_on) return null
  return (
    <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" role="status">
      HR3000 ist gekündigt. Alle Daten werden am <strong>{formatDate(plan.deletion_due_on)}</strong> endgültig gelöscht
      – bitte vorher exportieren (<Link to="/auswertungen" className="underline">Analysen</Link>,{' '}
      <Link to="/lohn-export" className="underline">Lohn-Export</Link>).
      {isAdmin && (
        <>
          {' '}
          Zurücknehmen unter{' '}
          <Link to="/einstellungen/konto" className="underline">
            Einstellungen
          </Link>
          .
        </>
      )}
    </div>
  )
}
