import { useState } from 'react'
import { ApiError } from '../../api/client'
import {
  useAttributeSectionsQuery,
  useDeleteAttributeValueMutation,
  useEmployeeAttributesQuery,
  useEmployeeHistoryQuery,
  usePutAttributeMutation,
  type AttributeDefinition,
  type EmployeeAttributeValue,
} from '../../api/queries/attributes'
import { useEmployeesQuery } from '../../api/queries/employees'
import { formatDate, formatDateTime } from '../../lib/format'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

const SELECT_CLASS = 'h-9 rounded-md border border-slate-300 bg-white px-2 text-sm'

/** Personalakte → „Weitere Angaben“: eigene Felder je Abschnitt; Felder mit Verlauf mit „Gültig ab“. */
export function AttributesTab({ employeeId }: { employeeId: number }) {
  const sections = useAttributeSectionsQuery().data ?? []
  const values = useEmployeeAttributesQuery(employeeId).data ?? []
  const byId = new Map(values.map((value) => [value.attribute_id, value]))

  if (sections.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        Noch keine eigenen Felder. Admins legen sie unter „Einstellungen“ → „Felder der Personalakte“ an.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-6">
      {sections.map((section) => (
        <section key={section.id} className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-slate-900">{section.name}</h3>
          {section.attributes.map((attribute) => (
            <AttributeRow key={attribute.id} employeeId={employeeId} attribute={attribute} value={byId.get(attribute.id)} />
          ))}
        </section>
      ))}
    </div>
  )
}

function AttributeRow({
  employeeId,
  attribute,
  value,
}: {
  employeeId: number
  attribute: AttributeDefinition
  value: EmployeeAttributeValue | undefined
}) {
  const put = usePutAttributeMutation(employeeId)
  const remove = useDeleteAttributeValueMutation(employeeId)
  const people = useEmployeesQuery({ active: true }).data ?? []
  const [draft, setDraft] = useState<string | null>(null)
  const [validFrom, setValidFrom] = useState('')
  const [error, setError] = useState<string | null>(null)
  const current = draft ?? (attribute.field_type === 'NUMBER' ? value?.value?.replace('.', ',') : value?.value) ?? ''

  function save() {
    setError(null)
    put.mutate(
      { attributeId: attribute.id, value: current === '' ? null : current, validFrom: attribute.dated ? validFrom : undefined },
      {
        onSuccess: () => {
          setDraft(null)
          setValidFrom('')
        },
        onError: (err) => setError(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen.'),
      },
    )
  }

  const id = `attr-${attribute.id}`
  let input
  if (attribute.field_type === 'SELECT' || attribute.field_type === 'BOOLEAN' || attribute.field_type === 'EMPLOYEE') {
    const choices =
      attribute.field_type === 'SELECT'
        ? attribute.options.map((option) => [option, option])
        : attribute.field_type === 'BOOLEAN'
          ? [['true', 'Ja'], ['false', 'Nein']]
          : people.map((person) => [String(person.id), `${person.last_name}, ${person.first_name}`])
    input = (
      <select id={id} className={SELECT_CLASS} value={current} onChange={(e) => setDraft(e.target.value)}>
        <option value="">–</option>
        {choices.map(([key, text]) => (
          <option key={key} value={key}>
            {text}
          </option>
        ))}
      </select>
    )
  } else {
    input = (
      <Input
        id={id}
        className="w-64"
        type={attribute.field_type === 'DATE' ? 'date' : 'text'}
        inputMode={attribute.field_type === 'NUMBER' ? 'decimal' : undefined}
        value={current}
        onChange={(e) => setDraft(e.target.value)}
      />
    )
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={id} className="w-48 text-sm text-slate-700">
          {attribute.label}
        </label>
        {input}
        {attribute.dated && (
          <Input
            type="date"
            className="w-40"
            aria-label={`${attribute.label} gültig ab`}
            title="Gültig ab (leer = heute)"
            value={validFrom}
            onChange={(e) => setValidFrom(e.target.value)}
          />
        )}
        {(draft !== null || validFrom) && (
          <Button size="sm" onClick={save} disabled={put.isPending}>
            Speichern
          </Button>
        )}
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {attribute.dated && (value?.history ?? []).length > 0 && (
        <ul className="ml-48 flex flex-col gap-0.5 pl-2 text-xs text-slate-500">
          {(value?.history ?? []).map((entry) => (
            <li key={entry.id} className="flex items-center gap-2">
              <span>
                ab {entry.valid_from ? formatDate(entry.valid_from) : '–'}: {entry.value ?? 'leer'}
              </span>
              <button type="button" className="text-red-600 hover:underline" onClick={() => remove.mutate(entry.id)}>
                entfernen
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Personalakte → „Verlauf“: was sich am Mitarbeiter wann geändert hat. */
export function EmployeeHistoryTab({ employeeId }: { employeeId: number }) {
  const query = useEmployeeHistoryQuery(employeeId)
  if (query.isLoading) return <p className="text-slate-500">Lädt…</p>
  const entries = query.data ?? []
  if (entries.length === 0) return <p className="text-sm text-slate-500">Noch keine Änderungen protokolliert.</p>
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {entries.map((entry, index) => (
        <li key={index} className="flex flex-col border-b border-slate-100 pb-2">
          <span className="text-slate-900">{entry.what}</span>
          <span className="text-xs text-slate-500">
            {formatDateTime(entry.at)}
            {entry.by && ` · ${entry.by}`}
          </span>
        </li>
      ))}
    </ul>
  )
}
