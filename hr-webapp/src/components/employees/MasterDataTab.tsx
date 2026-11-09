import { useEffect, useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import type { Employee } from '../../api/queries/employees'
import {
  useCostCentersQuery,
  usePersonalDataQuery,
  useSetEmployeeCostCentersMutation,
  useUpdatePersonalDataMutation,
  type PersonalData,
  type PersonalDataInput,
} from '../../api/queries/personalData'
import { EMPLOYMENT_STATUS_LABELS } from '../../lib/labels'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

type Field = { key: keyof PersonalDataInput; label: string; type?: string; inputMode?: 'numeric' | 'decimal' | 'email' | 'tel' }

const CONTACT: Field[] = [
  { key: 'private_email', label: 'Private E-Mail', type: 'email' },
  { key: 'phone', label: 'Telefon', inputMode: 'tel' },
  { key: 'street', label: 'Straße und Hausnummer' },
  { key: 'zip_code', label: 'PLZ' },
  { key: 'city', label: 'Ort' },
  { key: 'country', label: 'Land' },
]
const PERSON: Field[] = [
  { key: 'nationality', label: 'Staatsangehörigkeit' },
  { key: 'birth_place', label: 'Geburtsort' },
  { key: 'birth_name', label: 'Geburtsname' },
  { key: 'children_count', label: 'Kinder', inputMode: 'numeric' },
  { key: 'child_allowance', label: 'Kinderfreibeträge', inputMode: 'decimal' },
]
const PAYROLL: Field[] = [
  { key: 'iban', label: 'IBAN' },
  { key: 'bic', label: 'BIC' },
  { key: 'account_holder', label: 'Kontoinhaber' },
  { key: 'tax_id', label: 'Steuer-ID', inputMode: 'numeric' },
  { key: 'tax_class', label: 'Steuerklasse', inputMode: 'numeric' },
  { key: 'church_tax', label: 'Konfession' },
  { key: 'social_security_number', label: 'Sozialversicherungsnummer' },
  { key: 'health_insurance', label: 'Krankenkasse' },
]
const NUMBER_FIELDS = new Set(['children_count', 'tax_class', 'child_allowance'])

function toForm(data: PersonalData | undefined): Record<string, string> {
  const form: Record<string, string> = {}
  for (const field of [...CONTACT, ...PERSON, ...PAYROLL]) {
    const value = data?.[field.key]
    form[field.key] = value === null || value === undefined ? '' : String(value).replace('.', field.key === 'child_allowance' ? ',' : '.')
  }
  return form
}

/** Personalakte → „Stammdaten“: Status, Kostenstellen, Kontakt/Adresse, Person/Familie und – mit
 * „Vergütung & Lohn-Export“ – Bank, Steuer, Sozialversicherung. */
export function MasterDataTab({ employee }: { employee: Employee }) {
  const query = usePersonalDataQuery(employee.id)
  const update = useUpdatePersonalDataMutation(employee.id)
  const [form, setForm] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => setForm(toForm(query.data)), [query.data])

  const payrollVisible = query.data?.payroll_visible ?? false
  const fields = [...CONTACT, ...PERSON, ...(payrollVisible ? PAYROLL : [])]

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSaved(false)
    const original = toForm(query.data)
    const payload: Record<string, unknown> = {}
    for (const field of fields) {
      const value = form[field.key] ?? ''
      if (value === original[field.key]) continue
      payload[field.key] =
        value.trim() === '' ? null : NUMBER_FIELDS.has(field.key) ? Number(value.replace(',', '.')) : value
    }
    if (Object.keys(payload).length === 0) return setSaved(true)
    update.mutate(payload as PersonalDataInput, {
      onSuccess: () => setSaved(true),
      onError: (err) => setError(err instanceof ApiError ? err.message : 'Bitte die Eingaben prüfen (z. B. IBAN, Steuer-ID).'),
    })
  }

  const renderFields = (list: Field[]) => (
    <div className="grid gap-3 sm:grid-cols-2">
      {list.map((field) => (
        <div key={field.key} className="flex flex-col gap-1.5">
          <Label htmlFor={`pd-${field.key}`}>{field.label}</Label>
          <Input
            id={`pd-${field.key}`}
            type={field.type ?? 'text'}
            inputMode={field.inputMode}
            value={form[field.key] ?? ''}
            onChange={(event) => setForm({ ...form, [field.key]: event.target.value })}
          />
        </div>
      ))}
    </div>
  )

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-slate-600">
        Status: <strong>{EMPLOYMENT_STATUS_LABELS[employee.employment_status ?? 'ACTIVE']}</strong>
        <span className="text-slate-400"> (aus Eintritt, Austritt, „Aktiv“ und Elternzeit/Pflegezeit)</span>
      </p>
      <CostCenterEditor employee={employee} />
      {query.isLoading ? (
        <p className="text-slate-500">Lädt…</p>
      ) : (
        <form className="flex flex-col gap-6" onSubmit={handleSubmit}>
          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold text-slate-900">Kontakt und Adresse</h3>
            {renderFields(CONTACT)}
          </section>
          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold text-slate-900">Person und Familie</h3>
            {renderFields(PERSON)}
          </section>
          {payrollVisible ? (
            <section className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-slate-900">Lohn: Bank, Steuer, Sozialversicherung</h3>
              {renderFields(PAYROLL)}
            </section>
          ) : (
            <p className="text-xs text-slate-500">Bank, Steuer und Sozialversicherung nur mit „Vergütung & Lohn-Export“.</p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {saved && !error && <p className="text-sm text-emerald-700">Gespeichert.</p>}
          <Button type="submit" className="self-start" disabled={update.isPending}>
            Speichern
          </Button>
        </form>
      )}
    </div>
  )
}

function CostCenterEditor({ employee }: { employee: Employee }) {
  const costCenters = useCostCentersQuery(true).data ?? []
  const save = useSetEmployeeCostCentersMutation(employee.id)
  const [rows, setRows] = useState<{ id: string; percent: string }[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setRows((employee.cost_centers ?? []).map((share) => ({ id: String(share.cost_center_id), percent: String(share.percent) })))
  }, [employee.cost_centers])

  const total = rows.reduce((sum, row) => sum + (Number(row.percent) || 0), 0)
  const usable = costCenters.filter((c) => !c.archived || rows.some((row) => row.id === String(c.id)))

  function handleSave() {
    setError(null)
    save.mutate(
      rows.filter((row) => row.id).map((row) => ({ cost_center_id: Number(row.id), percent: Number(row.percent) })),
      { onError: (err) => setError(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen.') },
    )
  }

  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-900">Kostenstellen</h3>
      {costCenters.length === 0 ? (
        <p className="text-xs text-slate-500">Noch keine Kostenstellen – anlegen unter „Einstellungen“ → „Kostenstellen“.</p>
      ) : (
        <>
          {rows.map((row, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2">
              <Select value={row.id} onValueChange={(value) => setRows(rows.map((r, i) => (i === index ? { ...r, id: value } : r)))}>
                <SelectTrigger className="w-64" aria-label={`Kostenstelle ${index + 1}`}>
                  <SelectValue placeholder="Kostenstelle wählen" />
                </SelectTrigger>
                <SelectContent>
                  {usable.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.code} {c.name}
                      {c.archived ? ' (archiviert)' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                className="w-20"
                inputMode="numeric"
                aria-label={`Anteil ${index + 1} in Prozent`}
                value={row.percent}
                onChange={(event) => setRows(rows.map((r, i) => (i === index ? { ...r, percent: event.target.value } : r)))}
              />
              <span className="text-sm text-slate-500">%</span>
              <Button type="button" variant="ghost" size="sm" aria-label="Entfernen" onClick={() => setRows(rows.filter((_, i) => i !== index))}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRows([...rows, { id: '', percent: rows.length === 0 ? '100' : String(Math.max(0, 100 - total)) }])}
            >
              <Plus className="h-4 w-4" />
              Kostenstelle
            </Button>
            {rows.length > 0 && <span className={`text-sm ${total === 100 ? 'text-slate-500' : 'text-red-600'}`}>Summe {total} %</span>}
            <Button type="button" size="sm" disabled={save.isPending || (rows.length > 0 && total !== 100)} onClick={handleSave}>
              Kostenstellen speichern
            </Button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </>
      )}
    </section>
  )
}
