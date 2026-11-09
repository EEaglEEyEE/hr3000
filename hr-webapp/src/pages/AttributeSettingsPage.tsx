import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  EMPLOYEE_ACCESS_LABELS,
  FIELD_TYPE_LABELS,
  useAttributeSectionsQuery,
  useCreateAttributeMutation,
  useCreateSectionMutation,
  useUpdateAttributeMutation,
  useUpdateSectionMutation,
  type AttributeSection,
  type FieldType,
} from '../api/queries/attributes'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

const SELECT_CLASS = 'h-9 max-w-full rounded-md border border-slate-300 bg-white px-2 text-sm'

/** Eigene Felder der Personalakte: Abschnitte (mit Sichtbarkeit für Mitarbeiter) und Felder. */
export function AttributeSettingsPage() {
  const query = useAttributeSectionsQuery(true)
  const createSection = useCreateSectionMutation()
  const [name, setName] = useState('')
  const [access, setAccess] = useState<AttributeSection['employee_access']>('NONE')
  const [error, setError] = useState<string | null>(null)

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    createSection.mutate(
      { name, employee_access: access, sort_order: (query.data?.length ?? 0) * 10 },
      { onSuccess: () => setName(''), onError: (err) => setError(err instanceof ApiError ? err.message : 'Fehler.') },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Felder der Personalakte</h1>
      <p className="text-sm text-slate-500">
        Eigene Abschnitte und Felder (Text, Zahl, Datum, Auswahl, Ja/Nein, Person). Felder „mit Verlauf“ bekommen ein
        „Gültig ab“ und zeigen frühere Werte. Werte pflegst du am Mitarbeiter unter „Personalakte“ → „Weitere Angaben“.
      </p>
      <form className="flex flex-wrap items-end gap-2" onSubmit={handleCreate}>
        <div className="flex max-w-full flex-col gap-1.5">
          <Label htmlFor="section-name">Neuer Abschnitt</Label>
          <Input id="section-name" className="w-56 max-w-full" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex max-w-full flex-col gap-1.5">
          <Label htmlFor="section-access">Sichtbar</Label>
          <select
            id="section-access"
            className={SELECT_CLASS}
            value={access}
            onChange={(e) => setAccess(e.target.value as AttributeSection['employee_access'])}
          >
            {Object.entries(EMPLOYEE_ACCESS_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" disabled={createSection.isPending}>
          Abschnitt anlegen
        </Button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {(query.data ?? []).map((section) => (
        <SectionCard key={section.id} section={section} />
      ))}
    </div>
  )
}

function SectionCard({ section }: { section: AttributeSection }) {
  const updateSection = useUpdateSectionMutation()
  const createAttribute = useCreateAttributeMutation()
  const updateAttribute = useUpdateAttributeMutation()
  const [label, setLabel] = useState('')
  const [type, setType] = useState<FieldType>('TEXT')
  const [options, setOptions] = useState('')
  const [dated, setDated] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    createAttribute.mutate(
      {
        section_id: section.id,
        label,
        field_type: type,
        options: type === 'SELECT' ? options.split(',').map((o) => o.trim()).filter(Boolean) : [],
        dated,
        sort_order: section.attributes.length * 10,
      },
      {
        onSuccess: () => {
          setLabel('')
          setOptions('')
          setDated(false)
        },
        onError: (err) => setError(err instanceof ApiError ? err.message : 'Bitte die Eingaben prüfen.'),
      },
    )
  }

  return (
    <section className={`flex flex-col gap-3 rounded-md border border-slate-200 p-4 ${section.archived ? 'opacity-60' : ''}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold text-slate-900">
          {section.name}
          {section.archived && ' (archiviert)'}
        </h2>
        <div className="flex max-w-full flex-wrap items-center gap-2">
          <select
            aria-label={`Sichtbarkeit ${section.name}`}
            className={SELECT_CLASS}
            value={section.employee_access}
            onChange={(e) =>
              updateSection.mutate({ id: section.id, payload: { employee_access: e.target.value as AttributeSection['employee_access'] } })
            }
          >
            {Object.entries(EMPLOYEE_ACCESS_LABELS).map(([key, text]) => (
              <option key={key} value={key}>
                {text}
              </option>
            ))}
          </select>
          <Button variant="outline" size="sm" onClick={() => updateSection.mutate({ id: section.id, payload: { archived: !section.archived } })}>
            {section.archived ? 'Wiederherstellen' : 'Archivieren'}
          </Button>
        </div>
      </div>
      {section.attributes.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {section.attributes.map((attribute) => (
            <li key={attribute.id} className={`flex flex-wrap items-center justify-between gap-2 ${attribute.archived ? 'text-slate-400' : ''}`}>
              <span>
                {attribute.label}{' '}
                <span className="text-xs text-slate-500">
                  ({FIELD_TYPE_LABELS[attribute.field_type]}
                  {attribute.options.length > 0 && `: ${attribute.options.join(', ')}`}
                  {attribute.dated && ', mit Verlauf'})
                </span>
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => updateAttribute.mutate({ id: attribute.id, payload: { archived: !attribute.archived } })}
              >
                {attribute.archived ? 'Wiederherstellen' : 'Archivieren'}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form className="flex flex-wrap items-end gap-2" onSubmit={handleAdd}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`attr-label-${section.id}`}>Neues Feld</Label>
          <Input id={`attr-label-${section.id}`} className="w-48" required maxLength={100} value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="flex max-w-full flex-col gap-1.5">
          <Label htmlFor={`attr-type-${section.id}`}>Art</Label>
          <select id={`attr-type-${section.id}`} className={SELECT_CLASS} value={type} onChange={(e) => setType(e.target.value as FieldType)}>
            {Object.entries(FIELD_TYPE_LABELS).map(([key, text]) => (
              <option key={key} value={key}>
                {text}
              </option>
            ))}
          </select>
        </div>
        {type === 'SELECT' && (
          <div className="flex max-w-full flex-col gap-1.5">
            <Label htmlFor={`attr-options-${section.id}`}>Werte (mit Komma)</Label>
            <Input id={`attr-options-${section.id}`} className="w-56 max-w-full" value={options} onChange={(e) => setOptions(e.target.value)} />
          </div>
        )}
        <label className="flex h-9 items-center gap-1.5 text-sm">
          <input type="checkbox" checked={dated} onChange={(e) => setDated(e.target.checked)} />
          mit Verlauf
        </label>
        <Button type="submit" variant="outline" disabled={createAttribute.isPending}>
          Feld hinzufügen
        </Button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  )
}
