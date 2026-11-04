import { useEffect, useState } from 'react'
import type { Tenant } from '../../api/queries/tenants'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

/** Super-Admin: Firma mit allen Daten sofort endgültig löschen – nur mit eingetippter Subdomain. */
export function PurgeTenantDialog({
  tenant,
  pending,
  error,
  onOpenChange,
  onConfirm,
}: {
  tenant: Tenant | undefined
  pending: boolean
  error: string | null
  onOpenChange: (open: boolean) => void
  onConfirm: (confirmSubdomain: string) => void
}) {
  const [confirm, setConfirm] = useState('')
  useEffect(() => setConfirm(''), [tenant?.id])

  return (
    <Dialog open={tenant !== undefined} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Endgültig löschen – {tenant?.name}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 text-sm text-slate-700">
          <p>
            Löscht die Firma <strong>sofort</strong> mit allen Daten: Mitarbeiter, Zeiten, Abwesenheiten, Dokumente,
            Einstellungen und Zugänge. Das lässt sich nicht rückgängig machen. Für eine normale Kündigung mit 30 Tagen
            Exportfrist stattdessen „Kündigen“ verwenden.
          </p>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="purge-confirm">
              Zur Bestätigung die Subdomain eingeben: <span className="font-mono">{tenant?.subdomain}</span>
            </Label>
            <Input id="purge-confirm" autoComplete="off" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </div>
          {error && <p className="text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={pending || confirm.trim().toLowerCase() !== tenant?.subdomain}
            onClick={() => onConfirm(confirm.trim())}
          >
            {pending ? 'Lösche…' : 'Endgültig löschen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
