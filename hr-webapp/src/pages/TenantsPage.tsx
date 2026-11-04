import { useState } from 'react'
import { ExternalLink, Plus } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  useCancelTenantMutation,
  usePurgeTenantMutation,
  useResetTenantAdminPasswordMutation,
  useTenantsQuery,
  useUpdateTenantMutation,
  type Tenant,
  type TenantStatus,
} from '../api/queries/tenants'
import { OneTimeCredentialsDialog } from '../components/tenants/OneTimeCredentialsDialog'
import { TenantFormDialog } from '../components/tenants/TenantFormDialog'
import { ResetPasswordDialog } from '../components/shared/ResetPasswordDialog'
import { UpdateAdminEmailDialog } from '../components/tenants/UpdateAdminEmailDialog'
import { Badge, type BadgeProps } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { PLAN_LABELS } from '../api/queries/plan'
import { formatDate } from '../lib/format'
import { PurgeTenantDialog } from '../components/tenants/PurgeTenantDialog'

// Entspricht config.free_employee_limit im Backend (nur für den Hinweis in der Übersicht).
const FREE_LIMIT = 5

interface CredentialsDialogState {
  title: string
  email: string
  password: string
  notice: { kind: 'ok' | 'warning'; text: string } | null
}

function emailNotice(requested: boolean, emailed: boolean, recipient: string) {
  if (!requested) return null
  return emailed
    ? { kind: 'ok' as const, text: `Die Zugangsdaten wurden zusätzlich per E-Mail an ${recipient} gesendet.` }
    : {
        kind: 'warning' as const,
        text: 'Die E-Mail konnte nicht versendet werden (kein SMTP-Server der Plattform konfiguriert oder Versandfehler) – bitte das Passwort selbst übermitteln.',
      }
}

const STATUS_LABELS: Record<TenantStatus, string> = {
  ACTIVE: 'Aktiv',
  TRIAL: 'Trial',
  SUSPENDED: 'Gesperrt',
}

const STATUS_VARIANT: Record<TenantStatus, BadgeProps['variant']> = {
  ACTIVE: 'success',
  TRIAL: 'info',
  SUSPENDED: 'danger',
}

/** Adresse des Mandanten: der erste Hostname-Teil der Super-Admin-Adresse
 * (z.B. "admin") wird durch die Mandanten-Subdomain ersetzt – Protokoll, Port
 * und restliche Domain bleiben, funktioniert damit lokal wie in Produktion. */
function tenantUrl(subdomain: string): string {
  const baseHost = window.location.host.split('.').slice(1).join('.')
  return `${window.location.protocol}//${subdomain}.${baseHost}`
}

export function TenantsPage() {
  const tenantsQuery = useTenantsQuery()
  const updateTenant = useUpdateTenantMutation()
  const resetAdminPassword = useResetTenantAdminPasswordMutation()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingTenant, setEditingTenant] = useState<Tenant | undefined>(undefined)
  const [credentials, setCredentials] = useState<CredentialsDialogState | null>(null)
  const [resetError, setResetError] = useState<string | null>(null)
  const [resetTenant, setResetTenant] = useState<Tenant | undefined>(undefined)
  const [adminEmailTenant, setAdminEmailTenant] = useState<Tenant | undefined>(undefined)
  const [purgeTenant, setPurgeTenant] = useState<Tenant | undefined>(undefined)
  const cancelTenant = useCancelTenantMutation()
  const purge = usePurgeTenantMutation()

  function openCreateDialog() {
    setEditingTenant(undefined)
    setDialogOpen(true)
  }

  function openEditDialog(tenant: Tenant) {
    setEditingTenant(tenant)
    setDialogOpen(true)
  }

  function changeStatus(tenant: Tenant, status: TenantStatus) {
    updateTenant.mutate({ tenantId: tenant.id, payload: { status } })
  }

  function changePlan(tenant: Tenant, plan: Tenant['plan']) {
    updateTenant.mutate({ tenantId: tenant.id, payload: { plan } })
  }

  async function handleResetPassword(tenant: Tenant, sendEmail: boolean) {
    setResetError(null)
    try {
      const result = await resetAdminPassword.mutateAsync({ tenantId: tenant.id, sendEmail })
      setResetTenant(undefined)
      setCredentials({
        title: `Neues Passwort – ${tenant.name}`,
        email: result.admin_email,
        password: result.new_password,
        notice: emailNotice(sendEmail, result.emailed, result.admin_email),
      })
    } catch (err) {
      if (err instanceof ApiError && err.code === 'ADMIN_NOT_FOUND') {
        setResetError(`Für "${tenant.name}" existiert kein zurücksetzbarer Admin-Account.`)
      } else {
        setResetError('Zurücksetzen fehlgeschlagen.')
      }
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Mandanten</h1>
        <Button onClick={openCreateDialog}>
          <Plus className="h-4 w-4" />
          Neuer Mandant
        </Button>
      </div>

      {tenantsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {tenantsQuery.isError && <p className="text-red-600">Mandanten konnten nicht geladen werden.</p>}
      {resetError && <p className="text-sm text-red-600">{resetError}</p>}

      {tenantsQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Subdomain</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Tarif</TableHead>
              <TableHead>Aktive MA</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {tenantsQuery.data.map((tenant) => (
              <TableRow key={tenant.id}>
                <TableCell>
                  <div className="flex flex-col">
                    <span>{tenant.name}</span>
                    {tenant.self_signup && (
                      <span className="text-xs text-slate-500">
                        Selbst registriert{tenant.created_at ? ` am ${formatDate(tenant.created_at.slice(0, 10))}` : ''}
                        {tenant.contact_name ? ` · ${tenant.contact_name}` : ''}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-slate-500">{tenant.subdomain}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Badge variant={STATUS_VARIANT[tenant.status]}>{STATUS_LABELS[tenant.status]}</Badge>
                    <Select
                      value={tenant.status}
                      onValueChange={(value) => changeStatus(tenant, value as TenantStatus)}
                    >
                      <SelectTrigger className="h-7 w-28 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(STATUS_LABELS).map(([status, label]) => (
                          <SelectItem key={status} value={status}>
                            {label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {tenant.deletion_due_on && (
                    <span className="mt-1 block text-xs text-amber-700">
                      Gekündigt – Löschung am {formatDate(tenant.deletion_due_on)}
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <Select value={tenant.plan} onValueChange={(value) => changePlan(tenant, value as Tenant['plan'])}>
                    <SelectTrigger className="h-7 w-32 text-xs" aria-label={`Tarif von ${tenant.name}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(PLAN_LABELS).map(([plan, label]) => (
                        <SelectItem key={plan} value={plan}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell className="text-slate-600">
                  {tenant.active_employees ?? '–'}
                  {tenant.plan === 'FREE' && tenant.active_employees != null && tenant.active_employees >= FREE_LIMIT && (
                    <Badge variant="warning" className="ml-2">
                      Grenze
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={tenant.status === 'SUSPENDED'}
                    title={tenant.status === 'SUSPENDED' ? 'Mandant ist gesperrt' : tenantUrl(tenant.subdomain)}
                    onClick={() => window.open(tenantUrl(tenant.subdomain), '_blank', 'noopener')}
                  >
                    <ExternalLink className="h-4 w-4" />
                    Öffnen
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => openEditDialog(tenant)}>
                    Bearbeiten
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={resetAdminPassword.isPending}
                    onClick={() => {
                      setResetError(null)
                      setResetTenant(tenant)
                    }}
                  >
                    Passwort zurücksetzen
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setAdminEmailTenant(tenant)}>
                    Admin-E-Mail ändern
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={cancelTenant.isPending}
                    onClick={() => cancelTenant.mutate({ tenantId: tenant.id, revoke: tenant.deletion_due_on != null })}
                  >
                    {tenant.deletion_due_on ? 'Kündigung zurücknehmen' : 'Kündigen'}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-red-700"
                    onClick={() => {
                      purge.reset()
                      setPurgeTenant(tenant)
                    }}
                  >
                    Endgültig löschen…
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {tenantsQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-slate-500">
                  Noch keine Mandanten angelegt.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <PurgeTenantDialog
        tenant={purgeTenant}
        pending={purge.isPending}
        error={purge.isError ? (purge.error instanceof ApiError ? purge.error.message : 'Löschen fehlgeschlagen.') : null}
        onOpenChange={(open) => !open && setPurgeTenant(undefined)}
        onConfirm={(confirmSubdomain) =>
          purgeTenant &&
          purge.mutate({ tenantId: purgeTenant.id, confirmSubdomain }, { onSuccess: () => setPurgeTenant(undefined) })
        }
      />

      <TenantFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        tenant={editingTenant}
        onCreated={(result, emailRequested) =>
          setCredentials({
            title: `Mandant angelegt – ${result.name}`,
            email: result.admin_email,
            password: result.initial_admin_password,
            notice: emailNotice(emailRequested, result.credentials_emailed, result.admin_email),
          })
        }
      />

      <UpdateAdminEmailDialog
        open={adminEmailTenant !== undefined}
        onOpenChange={(open) => !open && setAdminEmailTenant(undefined)}
        tenantId={adminEmailTenant?.id}
        tenantName={adminEmailTenant?.name}
      />

      <OneTimeCredentialsDialog
        open={credentials !== null}
        onOpenChange={(open) => !open && setCredentials(null)}
        title={credentials?.title ?? ''}
        email={credentials?.email ?? ''}
        password={credentials?.password ?? ''}
        notice={credentials?.notice ?? null}
      />

      <ResetPasswordDialog
        open={resetTenant !== undefined}
        onOpenChange={(open) => !open && setResetTenant(undefined)}
        title={`Admin-Passwort zurücksetzen – ${resetTenant?.name ?? ''}`}
        description="Der Erst-Admin dieses Mandanten bekommt ein neues Einmalpasswort, das alte wird ungültig."
        recipient="die Admin-E-Mail des Mandanten"
        pending={resetAdminPassword.isPending}
        error={resetError}
        onConfirm={(sendEmail) => resetTenant && handleResetPassword(resetTenant, sendEmail)}
      />
    </div>
  )
}
