import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  useCreateDocumentCategoryMutation,
  useDocumentCategoriesQuery,
  useUpdateDocumentCategoryMutation,
  type DocumentCategoryDefinition,
} from '../api/documents'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

const FLAGS: { key: 'employee_upload' | 'employee_visible' | 'confidential'; label: string }[] = [
  { key: 'employee_upload', label: 'Mitarbeiter dürfen hochladen' },
  { key: 'employee_visible', label: 'für Mitarbeiter sichtbar (Vorgabe)' },
  { key: 'confidential', label: 'vertraulich (nur Admins)' },
]

/** Eigene Dokumentkategorien mit Rechten (neben den festen Kategorien). */
export function DocumentCategoriesPage() {
  const query = useDocumentCategoriesQuery()
  const create = useCreateDocumentCategoryMutation()
  const update = useUpdateDocumentCategoryMutation()
  const [name, setName] = useState('')
  const [flags, setFlags] = useState({ employee_upload: false, employee_visible: false, confidential: false })
  const [error, setError] = useState<string | null>(null)
  const onError = (err: Error) => setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.')

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    create.mutate({ name, ...flags }, { onSuccess: () => setName(''), onError })
  }

  function toggle(category: DocumentCategoryDefinition, key: (typeof FLAGS)[number]['key']) {
    setError(null)
    update.mutate({ id: category.id, payload: { [key]: !category[key] } }, { onError })
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Dokumentkategorien</h1>
      <p className="text-sm text-slate-500">
        Eigene Kategorien neben den festen (Vertrag, Bescheinigung, Krankmeldung …). In Kategorien mit „Mitarbeiter dürfen
        hochladen“ legen Mitarbeiter in „Mein Bereich“ → „Dokumente“ selbst Dateien ab; Admin und HR werden benachrichtigt.
      </p>
      <form className="flex flex-wrap items-end gap-3" onSubmit={handleCreate}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="doccat-name">Neue Kategorie</Label>
          <Input id="doccat-name" className="w-56" required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        {FLAGS.map((flag) => (
          <label key={flag.key} className="flex h-9 items-center gap-1.5 text-sm">
            <input type="checkbox" checked={flags[flag.key]} onChange={(e) => setFlags({ ...flags, [flag.key]: e.target.checked })} />
            {flag.label}
          </label>
        ))}
        <Button type="submit" disabled={create.isPending}>
          Anlegen
        </Button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="flex flex-col gap-2">
        {(query.data ?? []).map((category) => (
          <li
            key={category.id}
            className={`flex flex-wrap items-center gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm ${category.archived ? 'opacity-60' : ''}`}
          >
            <span className="min-w-40 font-medium">{category.name}</span>
            {FLAGS.map((flag) => (
              <label key={flag.key} className="flex items-center gap-1.5">
                <input type="checkbox" checked={category[flag.key]} onChange={() => toggle(category, flag.key)} />
                {flag.label}
              </label>
            ))}
            <Button variant="ghost" size="sm" onClick={() => update.mutate({ id: category.id, payload: { archived: !category.archived } })}>
              {category.archived ? 'Wiederherstellen' : 'Archivieren'}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}
