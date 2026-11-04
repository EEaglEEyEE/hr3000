import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import {
  useCreateTenantMutation,
  useUpdateTenantMutation,
  type Tenant,
  type TenantCreateResponse,
} from '../../api/queries/tenants'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

interface TenantFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tenant?: Tenant
  /** Wird nach erfolgreichem Anlegen mit dem Erst-Admin-Einmalpasswort
   * aufgerufen – die Anzeige übernimmt die aufrufende Seite. */
  onCreated?: (result: TenantCreateResponse, emailRequested: boolean) => void
}

const SUBDOMAIN_PATTERN = /^[a-z0-9-]{1,63}$/

export function TenantFormDialog({ open, onOpenChange, tenant, onCreated }: TenantFormDialogProps) {
  const isEditMode = tenant !== undefined
  const createTenant = useCreateTenantMutation()
  const updateTenant = useUpdateTenantMutation()

  const [name, setName] = useState('')
  const [subdomain, setSubdomain] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [sendCredentials, setSendCredentials] = useState(false)
  const [contactEmail, setContactEmail] = useState('')
  const [contactName, setContactName] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(tenant?.name ?? '')
    setSubdomain(tenant?.subdomain ?? '')
    setAdminEmail('')
    setSendCredentials(false)
    setContactEmail(tenant?.contact_email ?? '')
    setContactName(tenant?.contact_name ?? '')
    setError(null)
  }, [open, tenant])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      if (isEditMode) {
        await updateTenant.mutateAsync({
          tenantId: tenant.id,
          payload: { name, contact_email: contactEmail || null, contact_name: contactName || null },
        })
        onOpenChange(false)
      } else {
        const result = await createTenant.mutateAsync({
          subdomain,
          name,
          admin_email: adminEmail,
          contact_email: contactEmail || undefined,
          contact_name: contactName || undefined,
          send_credentials_email: sendCredentials,
          plan: 'FREE',
        })
        onOpenChange(false)
        onCreated?.(result, sendCredentials)
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === 'SUBDOMAIN_TAKEN') {
        setError('Diese Subdomain ist bereits vergeben.')
      } else {
        setError('Speichern fehlgeschlagen.')
      }
    }
  }

  const isSubmitting = createTenant.isPending || updateTenant.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Mandant bearbeiten' : 'Neuer Mandant'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tenant_name">Name</Label>
            <Input
              id="tenant_name"
              required
              placeholder="z.B. Musterfirma GmbH"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tenant_subdomain">Subdomain</Label>
            <Input
              id="tenant_subdomain"
              required
              disabled={isEditMode}
              pattern={SUBDOMAIN_PATTERN.source}
              placeholder="z.B. musterfirma"
              value={subdomain}
              onChange={(event) => setSubdomain(event.target.value.toLowerCase())}
            />
            <p className="text-xs text-slate-500">
              {isEditMode
                ? 'Kann nach dem Anlegen nicht mehr geändert werden.'
                : `Nur Kleinbuchstaben, Ziffern und Bindestriche. Ergibt die Login-Adresse ${subdomain || 'firma'}.${window.location.hostname.split('.').slice(1).join('.')}.`}
            </p>
          </div>
          {!isEditMode && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tenant_admin_email">E-Mail des Erst-Admins</Label>
              <Input
                id="tenant_admin_email"
                type="email"
                required
                placeholder="z.B. admin@acme.example"
                value={adminEmail}
                onChange={(event) => setAdminEmail(event.target.value)}
              />
              <p className="text-xs text-slate-500">
                Für diese Adresse wird sofort ein Admin-Zugang mit Einmalpasswort angelegt – ohne
                ihn gäbe es keinen Weg, sich bei diesem Mandanten anzumelden.
              </p>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300"
                  checked={sendCredentials}
                  onChange={(event) => setSendCredentials(event.target.checked)}
                />
                Zugangsdaten zusätzlich per E-Mail senden
              </label>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tenant_contact_name">Kontakt (Name, optional)</Label>
              <Input
                id="tenant_contact_name"
                value={contactName}
                onChange={(event) => setContactName(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tenant_contact_email">Kontakt-E-Mail (optional)</Label>
              <Input
                id="tenant_contact_email"
                type="email"
                value={contactEmail}
                onChange={(event) => setContactEmail(event.target.value)}
              />
            </div>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
