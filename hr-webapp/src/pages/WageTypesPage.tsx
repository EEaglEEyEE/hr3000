/** Lohnarten an einer Stelle (nur Admin): je Zeitart, je Zuschlag und je Zulagen-/Einmalzahlungsart.
 *  Grundlage für die DATEV-Datei; der CSV-Lohn-Export braucht keine Lohnarten. */
import { useEffect, useState, type FormEvent } from 'react'
import { Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useSetSurchargeWageTypeMutation, useSurchargeRulesQuery } from '../api/queries/surcharges'
import {
  useCreatePayComponentTypeMutation,
  useDeletePayComponentTypeMutation,
  usePayComponentTypesQuery,
  useUpdatePayComponentTypeMutation,
  useUpdateWageTypesMutation,
  useWageTypesQuery,
  type PayComponentType,
} from '../api/queries/wageTypes'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

const DIGITS = /^\d{0,6}$/
const KIND_LABELS: Record<PayComponentType['kind'], string> = { ALLOWANCE: 'Zulage', ONE_TIME: 'Einmalzahlung' }

export function WageTypesPage() {
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>, done?: string) {
    setError(null)
    setMessage(null)
    try {
      await action()
      if (done) setMessage(done)
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Angaben prüfen (Lohnart: bis zu 6 Ziffern).')
    }
  }

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Lohnarten</h1>
        <p className="text-sm text-slate-500">
          Alle Lohnarten an einer Stelle – für die DATEV-Datei auf der Seite „Lohn-Export“. Ohne Lohnart wird eine Position
          nicht übertragen; die Vorschau des DATEV-Exports nennt sie dann als Hinweis.
        </p>
      </div>
      {message && <p className="text-sm text-emerald-600">{message}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <TimeTypesSection run={run} />
      <SurchargesSection run={run} />
      <ComponentTypesSection run={run} />
    </div>
  )
}

type Run = (action: () => Promise<unknown>, done?: string) => Promise<void>

function TimeTypesSection({ run }: { run: Run }) {
  const query = useWageTypesQuery()
  const update = useUpdateWageTypesMutation()
  const [values, setValues] = useState<Record<string, string>>({})
  useEffect(() => {
    if (query.data) setValues(Object.fromEntries(query.data.items.map((i) => [i.item, i.wage_type ?? ''])))
  }, [query.data])
  const valid = Object.values(values).every((v) => DIGITS.test(v.trim()))

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void run(
      () => update.mutateAsync(Object.fromEntries(Object.entries(values).map(([item, value]) => [item, value.trim() || null]))),
      'Lohnarten gespeichert.',
    )
  }

  return (
    <form className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={save}>
      <div>
        <h2 className="font-medium text-slate-900">Zeitarten</h2>
        <p className="text-sm text-slate-500">
          Stunden gehen nur für Mitarbeiter mit Vergütung „Stundenlohn“ in die Datei, ausgezahlte Überstunden für alle.
          Arbeitszeit-Angaben ohne eigene Lohnart zählen als gearbeitete Stunden.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {(query.data?.items ?? []).map((item) => (
          <label key={item.item} className="flex items-center justify-between gap-3 text-sm">
            <span>{item.label}</span>
            <Input
              aria-label={`Lohnart ${item.label}`}
              inputMode="numeric"
              maxLength={6}
              className="w-28"
              placeholder={item.item === 'WORK_TIME' ? 'wie gearbeitet' : '–'}
              value={values[item.item] ?? ''}
              onChange={(e) => setValues((current) => ({ ...current, [item.item]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      <Button type="submit" className="self-start" disabled={!valid || update.isPending}>
        Lohnarten speichern
      </Button>
    </form>
  )
}

function SurchargesSection({ run }: { run: Run }) {
  const rulesQuery = useSurchargeRulesQuery()
  const setWageType = useSetSurchargeWageTypeMutation()
  const rules = rulesQuery.data ?? []
  return (
    <section className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div>
        <h2 className="font-medium text-slate-900">Zuschläge</h2>
        <p className="text-sm text-slate-500">
          Zuschlagsstunden je Regel. Regeln selbst bearbeiten unter{' '}
          <Link to="/einstellungen/zuschlaege" className="underline">
            Zuschläge
          </Link>
          .
        </p>
      </div>
      {rules.length === 0 && <p className="text-sm text-slate-500">Noch keine Zuschlagsregeln angelegt.</p>}
      <div className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {rules.map((rule) => (
          <label key={rule.id} className="flex items-center justify-between gap-3 text-sm">
            <span>
              {rule.name}
              {!rule.active && <span className="text-slate-400"> (inaktiv)</span>}
            </span>
            <Input
              aria-label={`Lohnart Zuschlag ${rule.name}`}
              inputMode="numeric"
              maxLength={6}
              className="w-28"
              defaultValue={rule.wage_type ?? ''}
              onBlur={(e) => {
                const value = e.target.value.trim()
                if (value !== (rule.wage_type ?? '') && DIGITS.test(value)) {
                  void run(() => setWageType.mutateAsync({ id: rule.id, wageType: value }), 'Lohnart gespeichert.')
                }
              }}
            />
          </label>
        ))}
      </div>
    </section>
  )
}

function ComponentTypesSection({ run }: { run: Run }) {
  const typesQuery = usePayComponentTypesQuery()
  const create = useCreatePayComponentTypeMutation()
  const update = useUpdatePayComponentTypeMutation()
  const remove = useDeletePayComponentTypeMutation()
  const [kind, setKind] = useState<PayComponentType['kind']>('ALLOWANCE')
  const [name, setName] = useState('')
  const [wageType, setWageType] = useState('')

  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void run(async () => {
      await create.mutateAsync({ kind, name: name.trim(), wage_type: wageType.trim() || null })
      setName('')
      setWageType('')
    }, 'Art angelegt.')
  }

  return (
    <section className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div>
        <h2 className="font-medium text-slate-900">Zulagen und Einmalzahlungen</h2>
        <p className="text-sm text-slate-500">
          Arten für „Zulagen &amp; Einmalzahlungen“ unter „Vertrag &amp; Vergütung“ – derselbe Name ergibt immer dieselbe Spalte
          im Lohn-Export. Inaktive Arten stehen bei neuen Einträgen nicht mehr zur Wahl, bestehende behalten sie.
        </p>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Bezeichnung</TableHead>
            <TableHead>Art</TableHead>
            <TableHead>Lohnart</TableHead>
            <TableHead>Aktiv</TableHead>
            <TableHead>Verwendet</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(typesQuery.data ?? []).map((item) => (
            <TableRow key={item.id}>
              <TableCell>
                <Input
                  aria-label={`Bezeichnung ${item.name}`}
                  maxLength={100}
                  className="w-56"
                  defaultValue={item.name}
                  onBlur={(e) => {
                    const value = e.target.value.trim()
                    if (value && value !== item.name) void run(() => update.mutateAsync({ id: item.id, payload: { name: value } }))
                  }}
                />
              </TableCell>
              <TableCell>{KIND_LABELS[item.kind]}</TableCell>
              <TableCell>
                <Input
                  aria-label={`Lohnart ${item.name}`}
                  inputMode="numeric"
                  maxLength={6}
                  className="w-24"
                  defaultValue={item.wage_type ?? ''}
                  onBlur={(e) => {
                    const value = e.target.value.trim()
                    if (value !== (item.wage_type ?? '') && DIGITS.test(value)) {
                      void run(() => update.mutateAsync({ id: item.id, payload: { wage_type: value } }), 'Lohnart gespeichert.')
                    }
                  }}
                />
              </TableCell>
              <TableCell>
                <input
                  type="checkbox"
                  aria-label={`${item.name} aktiv`}
                  checked={item.active}
                  onChange={(e) => void run(() => update.mutateAsync({ id: item.id, payload: { active: e.target.checked } }))}
                />
              </TableCell>
              <TableCell>{item.in_use}×</TableCell>
              <TableCell>
                {item.in_use === 0 && (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`${item.name} löschen`}
                    onClick={() => void run(() => remove.mutateAsync(item.id))}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
          {(typesQuery.data?.length ?? 0) === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-slate-500">
                Noch keine Arten – sie entstehen auch beim Anlegen einer Zulage.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <form className="flex flex-wrap items-end gap-3" onSubmit={add}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="type_kind">Art</Label>
          <select
            id="type_kind"
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={kind}
            onChange={(e) => setKind(e.target.value as PayComponentType['kind'])}
          >
            <option value="ALLOWANCE">Zulage</option>
            <option value="ONE_TIME">Einmalzahlung</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="type_name">Bezeichnung</Label>
          <Input id="type_name" maxLength={100} className="w-56" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="type_wage">Lohnart (optional)</Label>
          <Input id="type_wage" inputMode="numeric" maxLength={6} className="w-28" value={wageType} onChange={(e) => setWageType(e.target.value)} />
        </div>
        <Button type="submit" disabled={!name.trim() || !DIGITS.test(wageType.trim()) || create.isPending}>
          Art hinzufügen
        </Button>
      </form>
    </section>
  )
}
