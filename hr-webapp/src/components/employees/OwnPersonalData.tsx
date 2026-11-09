import { useMyAttributesQuery } from '../../api/queries/attributes'
import { useOwnPersonalDataQuery } from '../../api/queries/personalData'

const ROWS: { key: string; label: string }[] = [
  { key: 'private_email', label: 'Private E-Mail' },
  { key: 'phone', label: 'Telefon' },
  { key: 'street', label: 'Straße' },
  { key: 'zip_code', label: 'PLZ' },
  { key: 'city', label: 'Ort' },
  { key: 'country', label: 'Land' },
  { key: 'nationality', label: 'Staatsangehörigkeit' },
  { key: 'children_count', label: 'Kinder' },
  { key: 'iban', label: 'IBAN' },
  { key: 'tax_id', label: 'Steuer-ID' },
  { key: 'tax_class', label: 'Steuerklasse' },
  { key: 'social_security_number', label: 'Sozialversicherungsnummer' },
  { key: 'health_insurance', label: 'Krankenkasse' },
]

/** „Mein Bereich“ → „Meine Daten“: was die Firma über mich gespeichert hat (nur lesen). */
export function OwnPersonalData() {
  const query = useOwnPersonalDataQuery()
  if (query.isLoading) return <p className="text-slate-500">Lädt…</p>
  const data = (query.data ?? {}) as Record<string, unknown>
  const filled = ROWS.filter((row) => data[row.key] !== null && data[row.key] !== undefined && data[row.key] !== '')
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-600">Stimmt etwas nicht? Unten „Änderung vorschlagen“ – die Personalabteilung übernimmt es.</p>
      {filled.length === 0 ? (
        <p className="text-sm text-slate-500">Noch keine Angaben hinterlegt.</p>
      ) : (
        <dl className="grid max-w-xl grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
          {filled.map((row) => (
            <div key={row.key} className="contents">
              <dt className="text-slate-500">{row.label}</dt>
              <dd className="break-all text-slate-900">{String(data[row.key])}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

/** Eigene Felder der Firma, die Mitarbeiter sehen dürfen (Abschnitte „VIEW“/„EDIT“). */
export function OwnAttributes() {
  const query = useMyAttributesQuery()
  if (!query.data || query.data.sections.length === 0) return null
  const values = new Map(query.data.values.map((value) => [value.attribute_id, value]))
  return (
    <div className="flex flex-col gap-4">
      {query.data.sections.map((section) => (
        <section key={section.id} className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-slate-900">{section.name}</h3>
          <dl className="grid max-w-xl grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
            {section.attributes.map((attribute) => (
              <div key={attribute.id} className="contents">
                <dt className="text-slate-500">{attribute.label}</dt>
                <dd className="text-slate-900">{values.get(attribute.id)?.display ?? '–'}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  )
}
