import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  useDeleteRoleMutation,
  useRoleMetaQuery,
  useRolesQuery,
  useSaveRoleMutation,
  type Role,
  type RoleMeta,
} from '../api/queries/roles'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import type { Area, Level } from '../lib/access'

const LEVELS: { value: Level; label: string }[] = [
  { value: 'NONE', label: 'Kein Zugriff' },
  { value: 'VIEW', label: 'Ansehen' },
  { value: 'EDIT', label: 'Bearbeiten' },
]

type Permissions = Partial<Record<Area, Level>>

interface Draft {
  id?: number
  name: string
  description: string
  permissions: Permissions
}

const EMPTY: Draft = { name: '', description: '', permissions: {} }

function summary(role: Role, meta: RoleMeta | undefined): string {
  const parts = (meta?.areas ?? [])
    .filter((area) => role.permissions[area.key] && role.permissions[area.key] !== 'NONE')
    .map((area) => `${area.label}: ${role.permissions[area.key] === 'EDIT' ? 'bearbeiten' : 'ansehen'}`)
  return parts.join(' · ') || 'Kein Zugriff'
}

/** Einstellungen → „Rollen“ (nur Admin): eigene Rollen schränken HR-Konten auf einzelne Bereiche ein. */
export function RolesPage() {
  const rolesQuery = useRolesQuery()
  const metaQuery = useRoleMetaQuery()
  const save = useSaveRoleMutation()
  const remove = useDeleteRoleMutation()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const meta = metaQuery.data

  function startNew(template?: RoleMeta['templates'][number]) {
    setError(null)
    setDraft(
      template
        ? { name: template.name, description: template.description, permissions: { ...template.permissions } }
        : { ...EMPTY, permissions: {} },
    )
  }

  function startEdit(role: Role) {
    setError(null)
    setDraft({ id: role.id, name: role.name, description: role.description ?? '', permissions: { ...role.permissions } })
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!draft) return
    setError(null)
    if (!Object.values(draft.permissions).some((level) => level && level !== 'NONE')) {
      setError('Mindestens ein Bereich braucht „Ansehen“ oder „Bearbeiten“.')
      return
    }
    save.mutate(
      {
        id: draft.id,
        name: draft.name,
        description: draft.description.trim() || null,
        permissions: draft.permissions as RoleMeta['templates'][number]['permissions'],
      },
      {
        onSuccess: () => setDraft(null),
        onError: (err) => setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Speichern fehlgeschlagen.'),
      },
    )
  }

  function handleDelete(role: Role) {
    if (!window.confirm(`Rolle „${role.name}“ löschen?`)) return
    setError(null)
    remove.mutate(role.id, {
      onError: (err) => setError(err instanceof ApiError ? err.message : 'Löschen fehlgeschlagen.'),
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Rollen</h1>
        <p className="text-sm text-slate-500">
          Eigene Rollen schränken Konten mit der Verwaltungsrolle „HR“ auf einzelne Bereiche ein – sie geben nie
          mehr Rechte als HR. Zuweisen: am Mitarbeiter unter „Einstellungen“ → „HR-Berechtigung“ oder hier unter
          „Verwaltungskonten“. Vorschläge zu eigenen Daten machen Mitarbeiter weiterhin über „Mein Bereich“.
        </p>
      </div>

      {!draft && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => startNew()}>Neue Rolle</Button>
          {(meta?.templates ?? []).map((template) => (
            <Button key={template.key} variant="outline" onClick={() => startNew(template)} title={template.description}>
              Vorlage „{template.name}“
            </Button>
          ))}
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {draft && meta && (
        <form className="flex flex-col gap-4 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleSubmit}>
          <h2 className="text-base font-semibold text-slate-900">{draft.id ? 'Rolle bearbeiten' : 'Neue Rolle'}</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="role-name">Name</Label>
              <Input
                id="role-name"
                required
                maxLength={80}
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="role-description">Beschreibung</Label>
              <Input
                id="role-description"
                maxLength={500}
                value={draft.description}
                onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" aria-label="Rechte je Bereich">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="py-2 pr-2 font-medium">Bereich</th>
                  {LEVELS.map((level) => (
                    <th key={level.value} className="w-16 px-1 py-2 text-center text-xs font-medium sm:w-24 sm:px-2 sm:text-sm">
                      {level.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {meta.areas.map((area) => {
                  const current = draft.permissions[area.key] ?? 'NONE'
                  return (
                    <tr key={area.key} className="border-b border-slate-100">
                      <td className="py-2 pr-2">
                        <p className="font-medium text-slate-800">{area.label}</p>
                        <p className="hidden text-xs text-slate-500 sm:block">{area.description}</p>
                      </td>
                      {LEVELS.map((level) => (
                        <td key={level.value} className="px-1 py-2 text-center sm:px-2">
                          <input
                            type="radio"
                            className="h-4 w-4"
                            name={`area-${area.key}`}
                            aria-label={`${area.label}: ${level.label}`}
                            checked={current === level.value}
                            onChange={() =>
                              setDraft({ ...draft, permissions: { ...draft.permissions, [area.key]: level.value } })
                            }
                          />
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={save.isPending}>
              Speichern
            </Button>
            <Button type="button" variant="outline" onClick={() => setDraft(null)}>
              Abbrechen
            </Button>
          </div>
        </form>
      )}

      {rolesQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {rolesQuery.data && rolesQuery.data.length === 0 && !draft && (
        <p className="text-sm text-slate-500">Noch keine eigenen Rollen angelegt.</p>
      )}
      <ul className="flex flex-col gap-2">
        {(rolesQuery.data ?? []).map((role) => (
          <li
            key={role.id}
            className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-slate-200 bg-white p-3"
          >
            <div className="min-w-0">
              <p className="font-medium text-slate-900">
                {role.name}
                <span className="ml-2 text-xs font-normal text-slate-500">
                  {role.account_count === 1 ? '1 Konto' : `${role.account_count} Konten`}
                </span>
              </p>
              {role.description && <p className="text-sm text-slate-600">{role.description}</p>}
              <p className="text-xs text-slate-500">{summary(role, meta)}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => startEdit(role)}>
                Bearbeiten
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={role.account_count > 0}
                title={role.account_count > 0 ? 'Noch Konten zugewiesen' : undefined}
                onClick={() => handleDelete(role)}
              >
                Löschen
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
