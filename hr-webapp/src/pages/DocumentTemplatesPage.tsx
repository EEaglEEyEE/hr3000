import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  useDocumentCategoriesQuery,
  useDocumentTemplatesQuery,
  usePlaceholdersQuery,
  useSaveDocumentTemplateMutation,
  type DocumentCategory,
  type DocumentTemplate,
} from '../api/documents'
import { useAttributeSectionsQuery } from '../api/queries/attributes'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { DOCUMENT_CATEGORY_LABELS } from '../lib/labels'

const SELECT_CLASS = 'h-9 rounded-md border border-slate-300 bg-white px-2 text-sm'

/** Dokumentvorlagen mit Platzhaltern; erzeugt werden sie am Mitarbeiter („Aus Vorlage erstellen“). */
export function DocumentTemplatesPage() {
  const templates = useDocumentTemplatesQuery().data ?? []
  const [editing, setEditing] = useState<DocumentTemplate | null | undefined>(undefined)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Dokumentvorlagen</h1>
        <Button onClick={() => setEditing(null)}>Neue Vorlage</Button>
      </div>
      <p className="text-sm text-slate-500">
        Text mit Platzhaltern wie {'{{vorname}}'}; am Mitarbeiter unter „Personalakte“ → „Dokumente“ → „Aus Vorlage
        erstellen“ entsteht daraus ein PDF in der Akte (mit Firmenlogo).
      </p>
      {editing !== undefined ? (
        <TemplateForm template={editing} onClose={() => setEditing(undefined)} />
      ) : (
        <ul className="flex flex-col gap-2">
          {templates.map((template) => (
            <li
              key={template.id}
              className={`flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm ${template.archived ? 'opacity-60' : ''}`}
            >
              <span className="font-medium">
                {template.name}
                {template.archived && ' (archiviert)'}
              </span>
              <Button variant="outline" size="sm" onClick={() => setEditing(template)}>
                Bearbeiten
              </Button>
            </li>
          ))}
          {templates.length === 0 && <li className="text-sm text-slate-500">Noch keine Vorlagen.</li>}
        </ul>
      )}
    </div>
  )
}

function TemplateForm({ template, onClose }: { template: DocumentTemplate | null; onClose: () => void }) {
  const save = useSaveDocumentTemplateMutation()
  const placeholders = usePlaceholdersQuery().data ?? []
  const fields = (useAttributeSectionsQuery().data ?? []).flatMap((section) => section.attributes)
  const customCategories = (useDocumentCategoriesQuery().data ?? []).filter((c) => !c.archived)
  const [name, setName] = useState(template?.name ?? '')
  const [body, setBody] = useState(template?.body ?? '')
  const [category, setCategory] = useState(template?.category_id ? `c:${template.category_id}` : template?.category ?? 'OTHER')
  const [visible, setVisible] = useState(template?.employee_visible ?? false)
  const [archived, setArchived] = useState(template?.archived ?? false)
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const custom = category.startsWith('c:')
    save.mutate(
      {
        id: template?.id,
        payload: {
          name,
          body,
          category: (custom ? 'OTHER' : category) as DocumentCategory,
          category_id: custom ? Number(category.slice(2)) : null,
          employee_visible: visible,
          ...(template ? { archived } : {}),
        },
      },
      { onSuccess: onClose, onError: (err) => setError(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen.') },
    )
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
      <div className="flex flex-wrap gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tpl-name">Name</Label>
          <Input id="tpl-name" className="w-72" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tpl-category">Kategorie in der Akte</Label>
          <select id="tpl-category" className={SELECT_CLASS} value={category} onChange={(e) => setCategory(e.target.value)}>
            {Object.entries(DOCUMENT_CATEGORY_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
            {customCategories.map((c) => (
              <option key={c.id} value={`c:${c.id}`}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <label className="flex h-9 items-center gap-1.5 self-end text-sm">
          <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
          für Mitarbeiter sichtbar
        </label>
        {template && (
          <label className="flex h-9 items-center gap-1.5 self-end text-sm">
            <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />
            archiviert
          </label>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="tpl-body">Text</Label>
        <textarea
          id="tpl-body"
          required
          rows={14}
          maxLength={20000}
          className="rounded-md border border-slate-300 bg-white p-2 font-mono text-sm"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <p className="text-xs text-slate-500">
          Absätze durch Leerzeilen, „# “ am Zeilenanfang für eine Überschrift, **fett**. Platzhalter:{' '}
          {placeholders.map((p) => `{{${p.key}}}`).join(', ')}
          {fields.length > 0 && `, eigene Felder: ${fields.map((f) => `{{feld:${f.label}}}`).join(', ')}`}
        </p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          Speichern
        </Button>
        <Button type="button" variant="outline" onClick={onClose}>
          Abbrechen
        </Button>
      </div>
    </form>
  )
}
