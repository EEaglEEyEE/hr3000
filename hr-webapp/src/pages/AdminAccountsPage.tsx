import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  useCreateHrUserMutation,
  useDeleteHrUserMutation,
  useHrUsersQuery,
  useRolesQuery,
  useUpdateHrUserMutation,
  type HrUser,
} from '../api/queries/roles'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

type AccountRole = 'ADMIN' | 'HR'
const ROLE_LABELS: Record<string, string> = { ADMIN: 'Admin', HR: 'HR', SUPERVISOR: 'Führungskraft' }
const FULL_HR = '' // Auswahl „keine eigene Rolle“

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.status !== 422 ? err.message : fallback
}

/** Einstellungen → „Verwaltungskonten“ (nur Admin): Zugänge ohne Mitarbeiter, z. B. Steuerberatung oder
 * externes Lohnbüro. Zugänge von Mitarbeitern werden am Mitarbeiter gepflegt. */
export function AdminAccountsPage() {
  const usersQuery = useHrUsersQuery()
  const rolesQuery = useRolesQuery()
  const create = useCreateHrUserMutation()
  const update = useUpdateHrUserMutation()
  const remove = useDeleteHrUserMutation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<AccountRole>('HR')
  const [customRole, setCustomRole] = useState(FULL_HR)
  const [payroll, setPayroll] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const roles = rolesQuery.data ?? []

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    create.mutate(
      {
        email,
        password,
        role,
        payroll_access: role === 'HR' && customRole === FULL_HR && payroll,
        two_factor_enabled: false,
        custom_role_id: role === 'HR' && customRole !== FULL_HR ? Number(customRole) : null,
      },
      {
        onSuccess: () => {
          setEmail('')
          setPassword('')
          setCustomRole(FULL_HR)
          setPayroll(false)
        },
        onError: (err) => setError(errorText(err, 'Anlegen fehlgeschlagen – bitte Eingaben prüfen (Passwort mind. 8 Zeichen).')),
      },
    )
  }

  function changeCustomRole(user: HrUser, value: string) {
    setError(null)
    update.mutate(
      { id: user.id, custom_role_id: value === FULL_HR ? null : Number(value) },
      { onError: (err) => setError(errorText(err, 'Ändern fehlgeschlagen.')) },
    )
  }

  function handleRemove(user: HrUser) {
    if (!window.confirm(`Zugang von ${user.email} entfernen? Das Konto bleibt für den Verlauf bestehen.`)) return
    setError(null)
    remove.mutate(user.id, { onError: (err) => setError(errorText(err, 'Entfernen fehlgeschlagen.')) })
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Verwaltungskonten</h1>
        <p className="text-sm text-slate-500">
          Zugänge ohne Mitarbeiter, z. B. für die Steuerberatung (Rolle „HR“ mit der eigenen Rolle „Lohnbüro (nur
          lesen)“). Zugänge von Mitarbeitern pflegen Sie am Mitarbeiter.
        </p>
      </div>

      <form className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleCreate}>
        <div className="flex max-w-full flex-col gap-1.5">
          <Label htmlFor="account-email">E-Mail</Label>
          <Input
            id="account-email"
            type="email"
            required
            maxLength={255}
            className="w-64 max-w-full"
            placeholder="lohnbuero@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="flex max-w-full flex-col gap-1.5">
          <Label htmlFor="account-password">Passwort</Label>
          <Input
            id="account-password"
            type="password"
            required
            minLength={8}
            maxLength={72}
            autoComplete="new-password"
            className="w-48 max-w-full"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="account-role">Verwaltungsrolle</Label>
          <select
            id="account-role"
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={role}
            onChange={(event) => setRole(event.target.value as AccountRole)}
          >
            <option value="HR">HR</option>
            <option value="ADMIN">Admin</option>
          </select>
        </div>
        {role === 'HR' && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="account-custom-role">Eigene Rolle</Label>
            <select
              id="account-custom-role"
              className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
              value={customRole}
              onChange={(event) => setCustomRole(event.target.value)}
            >
              <option value={FULL_HR}>Keine (voller HR-Zugriff)</option>
              {roles.map((item) => (
                <option key={item.id} value={String(item.id)}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
        )}
        {role === 'HR' && customRole === FULL_HR && (
          <label className="flex h-9 items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={payroll}
              onChange={(event) => setPayroll(event.target.checked)}
            />
            Vergütung &amp; Lohn-Export
          </label>
        )}
        <Button type="submit" disabled={create.isPending}>
          Anlegen
        </Button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {usersQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      <ul className="flex flex-col gap-2" aria-label="Verwaltungskonten">
        {(usersQuery.data ?? []).map((user) => (
          <li
            key={user.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-white p-3"
          >
            <div className="min-w-0">
              <p className="break-words font-medium text-slate-900">{user.email}</p>
              <p className="text-sm text-slate-500">
                {ROLE_LABELS[user.role] ?? user.role}
                {user.role === 'HR' && !user.custom_role && user.payroll_access && ' · mit Vergütung & Lohn-Export'}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {user.role === 'HR' && (
                <select
                  aria-label={`Eigene Rolle von ${user.email}`}
                  className="h-8 max-w-full rounded-md border border-slate-300 bg-white px-2 text-sm"
                  value={user.custom_role ? String(user.custom_role.id) : FULL_HR}
                  onChange={(event) => changeCustomRole(user, event.target.value)}
                >
                  <option value={FULL_HR}>Keine eigene Rolle (voller HR-Zugriff)</option>
                  {roles.map((item) => (
                    <option key={item.id} value={String(item.id)}>
                      {item.name}
                    </option>
                  ))}
                </select>
              )}
              <Button variant="outline" size="sm" onClick={() => handleRemove(user)}>
                Zugang entfernen
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
