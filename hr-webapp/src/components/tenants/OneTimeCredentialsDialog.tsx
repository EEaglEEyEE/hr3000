import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Label } from '../ui/label'

interface OneTimeCredentialsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  email: string
  password: string
  /** Hinweis zum E-Mail-Versand (gesendet / nicht gesendet), optional. */
  notice?: { kind: 'ok' | 'warning'; text: string } | null
}

export function OneTimeCredentialsDialog({
  open,
  onOpenChange,
  title,
  email,
  password,
  notice,
}: OneTimeCredentialsDialogProps) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    await navigator.clipboard.writeText(password)
    setCopied(true)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setCopied(false)
        onOpenChange(next)
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>E-Mail</Label>
            <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800">
              {email}
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Einmalpasswort</Label>
            <div className="flex items-center gap-2">
              <p className="flex-1 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-800">
                {password}
              </p>
              <Button type="button" variant="outline" size="sm" onClick={handleCopy}>
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          {notice && (
            <p className={notice.kind === 'ok' ? 'text-sm text-emerald-600' : 'text-sm text-amber-700'}>
              {notice.text}
            </p>
          )}
          <p className="text-xs text-amber-700">
            Dieses Passwort wird nur jetzt angezeigt und ist danach nicht mehr abrufbar – jetzt
            sichern und sicher übermitteln.
          </p>
        </div>
        <DialogFooter>
          <Button type="button" onClick={() => onOpenChange(false)}>
            Schließen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
