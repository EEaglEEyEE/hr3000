import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { useUpdateTenantAdminEmailMutation } from '../../api/queries/tenants'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

interface UpdateAdminEmailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tenantId?: number
  tenantName?: string
  currentEmail?: string
  onUpdated?: (newEmail: string) => void
}

export function UpdateAdminEmailDialog({
  open,
  onOpenChange,
  tenantId,
  tenantName,
  currentEmail,
  onUpdated,
}: UpdateAdminEmailDialogProps) {
  const updateAdminEmail = useUpdateTenantAdminEmailMutation()
  const [newEmail, setNewEmail] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setNewEmail(currentEmail ?? '')
    setError(null)
  }, [open, currentEmail])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (tenantId === undefined) return
    setError(null)
    try {
      const result = await updateAdminEmail.mutateAsync({ tenantId, newEmail })
      onOpenChange(false)
      onUpdated?.(result.admin_email)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'EMAIL_TAKEN') {
        setError('Diese E-Mail wird bereits verwendet.')
      } else if (err instanceof ApiError && err.code === 'ADMIN_NOT_FOUND') {
        setError(`Für "${tenantName}" existiert kein Admin-Account.`)
      } else {
        setError('Ändern fehlgeschlagen.')
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Admin-E-Mail ändern – {tenantName}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new_admin_email">Neue E-Mail</Label>
            <Input
              id="new_admin_email"
              type="email"
              required
              value={newEmail}
              onChange={(event) => setNewEmail(event.target.value)}
            />
            <p className="text-xs text-slate-500">
              Wirkt auf den ältesten Admin-Account dieses Mandanten. Das Passwort bleibt unverändert.
            </p>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={updateAdminEmail.isPending}>
              {updateAdminEmail.isPending ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
