import { useEffect, useState } from 'react'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'

/** Bestätigung für "Passwort zurücksetzen": das neue Einmalpasswort wird
 * entweder per E-Mail zugestellt oder dem Admin einmalig angezeigt. */
export function ResetPasswordDialog({
  open,
  onOpenChange,
  title,
  description,
  recipient,
  pending,
  error,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  recipient: string
  pending: boolean
  error: string | null
  onConfirm: (sendEmail: boolean) => void
}) {
  const [sendEmail, setSendEmail] = useState(false)

  useEffect(() => {
    if (open) setSendEmail(false)
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <p className="text-sm text-slate-600">{description}</p>
          <label className="flex items-start gap-3 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-slate-300"
              checked={sendEmail}
              onChange={(event) => setSendEmail(event.target.checked)}
            />
            <span>
              Zugangsdaten per E-Mail an <span className="font-medium">{recipient}</span> senden
              <span className="block text-xs text-slate-500">
                Ohne Haken wird das Einmalpasswort einmalig hier angezeigt.
              </span>
            </span>
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button type="button" disabled={pending} onClick={() => onConfirm(sendEmail)}>
            {pending ? 'Setze zurück…' : 'Passwort zurücksetzen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
