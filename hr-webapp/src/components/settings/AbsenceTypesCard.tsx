import { useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import {
  useAbsenceTypesQuery,
  useCreateAbsenceTypeMutation,
  useUpdateAbsenceTypeMutation,
  type AbsenceTypeDef,
  type AbsenceTypeUpdateRequest,
} from '../../api/queries/absenceTypes'
import { ABSENCE_CATEGORY_HINTS, ABSENCE_TYPE_LABELS } from '../../lib/labels'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { SettingsCard } from './DefaultsSettingsCard'

type Category = AbsenceTypeDef['category']

/** Eigene Abwesenheitsarten: Name, Farbe, Kategorie (wie der Tag zählt), Genehmigung, Nachweis. */
export function AbsenceTypesCard() {
  const typesQuery = useAbsenceTypesQuery()
  const update = useUpdateAbsenceTypeMutation()
  const [error, setError] = useState<string | null>(null)

  async function patch(typeId: number, payload: Partial<AbsenceTypeUpdateRequest>) {
    setError(null)
    try {
      await update.mutateAsync({ typeId, payload })
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Eingaben prüfen.')
    }
  }

  return (
    <SettingsCard
      title="Abwesenheitsarten"
      description="Die Kategorie legt fest, wie ein Tag zählt. Wird sie geändert, werden bestehende Einträge dieser Art neu berechnet (nicht möglich, wenn Einträge in abgeschlossenen Monaten liegen). Nicht mehr benötigte Arten deaktivieren – bestehende Einträge behalten ihre Art."
      error={error}
    >
      <div className="flex flex-col divide-y divide-slate-100">
        {(typesQuery.data ?? []).map((type) => (
          <AbsenceTypeRow key={type.id} type={type} onPatch={(payload) => void patch(type.id, payload)} />
        ))}
      </div>
    </SettingsCard>
  )
}

function AbsenceTypeRow({
  type,
  onPatch,
}: {
  type: AbsenceTypeDef
  onPatch: (payload: Partial<AbsenceTypeUpdateRequest>) => void
}) {
  const [name, setName] = useState(type.name)
  const [certificate, setCertificate] = useState(type.certificate_from_day ? String(type.certificate_from_day) : '')

  return (
    <div className={`flex flex-col gap-2 py-3 ${type.active ? '' : 'opacity-60'}`}>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="color"
          aria-label="Farbe"
          className="h-8 w-8 cursor-pointer rounded border border-slate-200 bg-white p-0.5"
          value={type.color}
          onChange={(e) => onPatch({ color: e.target.value })}
        />
        <Input
          className="h-8 w-44"
          value={name}
          maxLength={60}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => name.trim() && name !== type.name && onPatch({ name: name.trim() })}
        />
        <select
          aria-label={`Kategorie von ${type.name}`}
          title={ABSENCE_CATEGORY_HINTS[type.category]}
          className="h-8 max-w-full rounded-md border border-slate-300 bg-white px-2 text-sm"
          value={type.category}
          onChange={(e) => {
            const next = e.target.value as Category
            if (
              window.confirm(
                `Kategorie von „${type.name}“ auf „${ABSENCE_TYPE_LABELS[next]}“ ändern? Bestehende Einträge dieser Art werden neu berechnet (Gleitzeit- und Urlaubskonto).`,
              )
            ) {
              onPatch({ category: next })
            }
          }}
        >
          {Object.entries(ABSENCE_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        {!type.active && <Badge variant="warning">deaktiviert</Badge>}
        <Button size="sm" variant="ghost" className="ml-auto" onClick={() => onPatch({ active: !type.active })}>
          {type.active ? 'Deaktivieren' : 'Aktivieren'}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pl-10 text-sm text-slate-600">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={type.employee_can_request}
            onChange={(e) => onPatch({ employee_can_request: e.target.checked })}
          />
          Mitarbeiter dürfen selbst beantragen
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={type.requires_approval}
            onChange={(e) => onPatch({ requires_approval: e.target.checked })}
          />
          Genehmigung nötig
        </label>
        {type.requires_approval && (
          <label className="flex max-w-full flex-wrap items-center gap-1.5">
            Genehmigt von
            <select
              aria-label={`Genehmigung bei ${type.name}`}
              className="h-7 max-w-full rounded-md border border-slate-300 bg-white px-1 text-sm"
              value={type.approval_chain ?? 'DEFAULT'}
              onChange={(e) =>
                onPatch({ approval_chain: e.target.value as 'DEFAULT' | 'SUPERVISOR' | 'SUPERVISOR_HR' | 'HR' })
              }
            >
              <option value="DEFAULT">Führungskraft (oder darüber) oder Admin/HR</option>
              <option value="SUPERVISOR">Führungskraft</option>
              <option value="SUPERVISOR_HR">erst Führungskraft, dann Admin/HR</option>
              <option value="HR">nur Admin/HR</option>
            </select>
          </label>
        )}
        <label
          className="flex items-center gap-1.5"
          title={type.category === 'SICK' || type.category === 'CHILD_SICK' ? 'Bei Krankheit nicht erlaubt (Gesundheitsdaten)' : undefined}
        >
          <input
            type="checkbox"
            checked={type.comment_required}
            disabled={type.category === 'SICK' || type.category === 'CHILD_SICK'}
            onChange={(e) => onPatch({ comment_required: e.target.checked })}
          />
          Kommentar erforderlich
        </label>
        <label className="flex max-w-full flex-wrap items-center gap-1.5">
          Im Abteilungskalender
          <select
            aria-label={`Abteilungskalender bei ${type.name}`}
            className="h-7 max-w-full rounded-md border border-slate-300 bg-white px-1 text-sm"
            value={type.calendar_visibility}
            onChange={(e) => onPatch({ calendar_visibility: e.target.value as 'GREY' | 'COLOR' })}
          >
            <option value="GREY">ausgegraut</option>
            <option value="COLOR">farbig (mit Art)</option>
          </select>
        </label>
        <label className="flex max-w-full flex-wrap items-center gap-1.5">
          Vertretung
          <select
            aria-label={`Vertretung bei ${type.name}`}
            className="h-7 max-w-full rounded-md border border-slate-300 bg-white px-1 text-sm"
            value={type.substitute_mode}
            onChange={(e) => onPatch({ substitute_mode: e.target.value as 'NONE' | 'OPTIONAL' | 'REQUIRED' })}
          >
            <option value="NONE">nicht abfragen</option>
            <option value="OPTIONAL">optional</option>
            <option value="REQUIRED">Pflicht beim Antrag</option>
          </select>
        </label>
        <label className="flex max-w-full flex-wrap items-center gap-1.5">
          Nachweis ab Tag
          <Input
            className="h-7 w-16 px-1 text-center"
            inputMode="numeric"
            placeholder="–"
            value={certificate}
            onChange={(e) => setCertificate(e.target.value.replace(/\D/g, '').slice(0, 3))}
            onBlur={() => {
              const value = certificate ? Number(certificate) : null
              if (value === (type.certificate_from_day ?? null)) return
              onPatch(value ? { certificate_from_day: value } : { clear_certificate_from_day: true })
            }}
          />
        </label>
      </div>
    </div>
  )
}

/** Neue Abwesenheitsart anlegen. */
export function NewAbsenceTypeCard() {
  const create = useCreateAbsenceTypeMutation()
  const [name, setName] = useState('')
  const [color, setColor] = useState('#f97316')
  const [category, setCategory] = useState<Category>('SPECIAL_LEAVE')
  const [requiresApproval, setRequiresApproval] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setMessage(null)
    try {
      await create.mutateAsync({
        name: name.trim(),
        color,
        category,
        requires_approval: requiresApproval,
        employee_can_request: true,
        substitute_mode: 'NONE',
        comment_required: false,
        calendar_visibility: 'GREY',
        approval_chain: 'DEFAULT',
        sort_order: 100,
      })
      setMessage(`„${name.trim()}“ angelegt.`)
      setName('')
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Eingaben prüfen.')
    }
  }

  return (
    <SettingsCard
      title="Neue Abwesenheitsart"
      description="z. B. „Kind krank“ (Krankheit), „Berufsschule“ oder „Fortbildung“ (bezahlte Freistellung), „Elternzeit“ (unbezahlt), „Gleittag“ (Freizeitausgleich)."
      message={message}
      error={error}
    >
      <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
        <div className="flex items-center gap-2">
          <input
            type="color"
            aria-label="Farbe"
            className="h-9 w-9 cursor-pointer rounded border border-slate-200 bg-white p-0.5"
            value={color}
            onChange={(e) => setColor(e.target.value)}
          />
          <Input placeholder="Name" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Select value={category} onValueChange={(value) => setCategory(value as Category)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(ABSENCE_CATEGORY_HINTS).map(([value, hint]) => (
              <SelectItem key={value} value={value}>
                {hint}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={requiresApproval} onChange={(e) => setRequiresApproval(e.target.checked)} />
          Selbst gestellte Anträge brauchen eine Genehmigung
        </label>
        <div>
          <Button type="submit" size="sm" disabled={!name.trim() || create.isPending}>
            Anlegen
          </Button>
        </div>
      </form>
    </SettingsCard>
  )
}
