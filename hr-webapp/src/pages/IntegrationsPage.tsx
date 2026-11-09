import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { formatDateTime } from '../lib/format'

const SCOPES: Record<string, string> = {
  'employees:read': 'Mitarbeiter lesen',
  'absences:read': 'Abwesenheiten lesen',
  'attendances:read': 'Stempelungen lesen',
}
const EVENTS: Record<string, string> = {
  'employee.created': 'Mitarbeiter angelegt',
  'employee.updated': 'Mitarbeiter geändert',
  'absence.created': 'Abwesenheit eingetragen/beantragt',
  'absence.decided': 'Antrag entschieden',
}

function Checkboxes({ options, value, onChange }: { options: Record<string, string>; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-3">
      {Object.entries(options).map(([key, label]) => (
        <label key={key} className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={value.includes(key)}
            onChange={(e) => onChange(e.target.checked ? [...value, key] : value.filter((v) => v !== key))}
          />
          {label}
        </label>
      ))}
    </div>
  )
}

/** Einstellungen → „API & Webhooks“ (nur Admins). Secrets werden nur einmal angezeigt. */
export function IntegrationsPage() {
  const queryClient = useQueryClient()
  const clients = useQuery({ queryKey: ['api-clients'], queryFn: async () => unwrap(await apiClient.GET('/api-clients')) }).data ?? []
  const hooks = useQuery({ queryKey: ['webhooks'], queryFn: async () => unwrap(await apiClient.GET('/webhooks')) }).data ?? []
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['api-clients'] })
    void queryClient.invalidateQueries({ queryKey: ['webhooks'] })
  }
  const createClient = useMutation({
    mutationFn: async (body: { name: string; scopes: string[] }) => unwrap(await apiClient.POST('/api-clients', { body })),
    onSuccess: refresh,
  })
  const revokeClient = useMutation({
    mutationFn: async (id: number) => apiClient.DELETE('/api-clients/{client_id}', { params: { path: { client_id: id } } }),
    onSuccess: refresh,
  })
  const createHook = useMutation({
    mutationFn: async (body: { url: string; events: string[] }) => unwrap(await apiClient.POST('/webhooks', { body })),
    onSuccess: refresh,
  })
  const toggleHook = useMutation({
    mutationFn: async ({ id, active }: { id: number; active: boolean }) =>
      unwrap(await apiClient.PATCH('/webhooks/{webhook_id}', { params: { path: { webhook_id: id } }, body: { active } })),
    onSuccess: refresh,
  })
  const deleteHook = useMutation({
    mutationFn: async (id: number) => apiClient.DELETE('/webhooks/{webhook_id}', { params: { path: { webhook_id: id } } }),
    onSuccess: refresh,
  })
  const testHook = useMutation({
    mutationFn: async (id: number) => unwrap(await apiClient.POST('/webhooks/{webhook_id}/test', { params: { path: { webhook_id: id } } })),
    onSuccess: () => setTimeout(refresh, 20_000),
  })

  const [clientName, setClientName] = useState('')
  const [scopes, setScopes] = useState<string[]>(['employees:read'])
  const [url, setUrl] = useState('')
  const [events, setEvents] = useState<string[]>(['employee.created'])
  const [secretShown, setSecretShown] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const onError = (err: Error) => setError(err instanceof ApiError ? err.message : 'Bitte die Eingaben prüfen.')

  function handleClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    createClient.mutate(
      { name: clientName, scopes },
      {
        onSuccess: (created) => {
          setClientName('')
          setSecretShown(`Client-ID: ${created.client_id}\nSecret: ${created.client_secret}`)
        },
        onError,
      },
    )
  }

  function handleHook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    createHook.mutate(
      { url, events },
      {
        onSuccess: (created) => {
          setUrl('')
          setSecretShown(`Signatur-Secret für ${created.url}:\n${created.secret}`)
        },
        onError,
      },
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-lg font-semibold text-slate-900">API & Webhooks</h1>
      <p className="text-sm text-slate-500">
        Für Fremdsysteme (z. B. Lohnsoftware, Zutritt, BI). Die API liest nur; Adresse: https://{'<firma>'}.hr3000.de/api/v1/ –
        Einzelheiten im Handbuch unter „API & Webhooks“.
      </p>
      {secretShown && (
        <div className="flex flex-col gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
          <p className="font-medium">Nur jetzt sichtbar – bitte sicher ablegen (z. B. im Passwort-Manager):</p>
          <pre className="whitespace-pre-wrap break-all font-mono text-xs" data-testid="secret">{secretShown}</pre>
          <Button size="sm" variant="outline" className="self-start" onClick={() => setSecretShown(null)}>
            Gesichert – ausblenden
          </Button>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <section className="flex flex-col gap-3">
        <h2 className="font-semibold text-slate-900">API-Zugänge</h2>
        <form className="flex flex-col gap-2" onSubmit={handleClient}>
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex max-w-full flex-col gap-1.5">
              <Label htmlFor="api-name">Name</Label>
              <Input id="api-name" className="w-56 max-w-full" required maxLength={100} value={clientName} onChange={(e) => setClientName(e.target.value)} />
            </div>
            <Button type="submit" disabled={createClient.isPending || scopes.length === 0}>
              Zugang anlegen
            </Button>
          </div>
          <Checkboxes options={SCOPES} value={scopes} onChange={setScopes} />
        </form>
        <ul className="flex flex-col gap-2 text-sm">
          {clients.map((c) => (
            <li key={c.id} className={`flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 px-3 py-2 ${c.revoked_at ? 'opacity-60' : ''}`}>
              <span className="min-w-0">
                <strong>{c.name}</strong> <span className="break-all font-mono text-xs">{c.client_id}</span>
                <span className="block text-xs text-slate-500">
                  {c.scopes.map((s) => SCOPES[s] ?? s).join(', ')}
                  {c.last_used_at && ` · zuletzt ${formatDateTime(c.last_used_at)}`}
                  {c.revoked_at && ' · gesperrt'}
                </span>
              </span>
              {!c.revoked_at && (
                <Button size="sm" variant="outline" onClick={() => revokeClient.mutate(c.id)}>
                  Sperren
                </Button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-semibold text-slate-900">Webhooks</h2>
        <form className="flex flex-col gap-2" onSubmit={handleHook}>
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex max-w-full flex-col gap-1.5">
              <Label htmlFor="hook-url">Adresse (https)</Label>
              <Input id="hook-url" className="w-96 max-w-full" required type="url" value={url} onChange={(e) => setUrl(e.target.value)} />
            </div>
            <Button type="submit" disabled={createHook.isPending || events.length === 0}>
              Webhook anlegen
            </Button>
          </div>
          <Checkboxes options={EVENTS} value={events} onChange={setEvents} />
        </form>
        <ul className="flex flex-col gap-2 text-sm">
          {hooks.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 px-3 py-2">
              <span className="min-w-0">
                <span className="break-all font-mono text-xs">{h.url}</span>
                <span className="block text-xs text-slate-500">
                  {h.events.map((e) => EVENTS[e] ?? e).join(', ')}
                  {h.last_status && ` · ${h.last_status}`}
                  {!h.active && ' · pausiert'}
                </span>
              </span>
              <span className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => testHook.mutate(h.id)}>
                  Test senden
                </Button>
                <Button size="sm" variant="outline" onClick={() => toggleHook.mutate({ id: h.id, active: !h.active })}>
                  {h.active ? 'Pausieren' : 'Fortsetzen'}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => deleteHook.mutate(h.id)}>
                  Löschen
                </Button>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
