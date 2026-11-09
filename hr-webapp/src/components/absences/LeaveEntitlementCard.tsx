import { useEffect, useState } from 'react'
import {
  useCreateLeaveAdjustmentMutation,
  useDeleteLeaveAdjustmentMutation,
  useLeaveAdjustmentsQuery,
  useLeaveEntitlementQuery,
  useUpdateLeaveEntitlementMutation,
} from '../../api/queries/leaveEntitlements'
import { ApiError } from '../../api/client'
import { formatDate, formatDays } from '../../lib/format'
import { Button } from '../ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

export function LeaveEntitlementCard({
  employeeId,
  readOnly = false,
}: {
  employeeId: number
  readOnly?: boolean
}) {
  const [year, setYear] = useState(() => new Date().getFullYear())
  const entitlementQuery = useLeaveEntitlementQuery(employeeId, year)
  const updateEntitlement = useUpdateLeaveEntitlementMutation(employeeId, year)

  const [entitledDays, setEntitledDays] = useState(0)
  const [carriedOverDays, setCarriedOverDays] = useState(0)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    if (entitlementQuery.data) {
      setEntitledDays(entitlementQuery.data.entitled_days)
      setCarriedOverDays(entitlementQuery.data.carried_over_days)
    }
  }, [entitlementQuery.data])

  async function handleSave() {
    // Nur Geändertes mitschicken – sonst würden berechneter Anspruch bzw. automatischer Übertrag
    // festgeschrieben.
    const entitledChanged = entitledDays !== entitlementQuery.data?.entitled_days
    const carriedChanged = carriedOverDays !== entitlementQuery.data?.carried_over_days
    if (entitledChanged || carriedChanged) {
      await updateEntitlement.mutateAsync({
        ...(entitledChanged ? { entitled_days: entitledDays } : {}),
        ...(carriedChanged ? { carried_over_days: carriedOverDays } : {}),
      })
    }
    setEditing(false)
  }

  // Berechneter Anspruch (null = nach Aufwand, HR trägt ein)
  const computed = entitlementQuery.data?.suggested_entitled_days ?? null

  return (
    <Card className="max-w-md">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Urlaubsanspruch {year}</CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => setYear(year - 1)}>
              ←
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setYear(year + 1)}>
              →
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {entitlementQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
        {entitlementQuery.data && !editing && (
          <div className="flex flex-col gap-2">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <span className="text-slate-500">
                Anspruch{entitlementQuery.data.entitled_manual ? ' (fest eingetragen)' : computed !== null ? ' (berechnet)' : ''}
              </span>
              <span className="text-right">{formatDays(entitlementQuery.data.entitled_days)} Tage</span>
              <span className="text-slate-500">
                Übertrag Vorjahr{entitlementQuery.data.carried_over_auto ? ' (automatisch)' : ''}
              </span>
              <span className="text-right">{formatDays(entitlementQuery.data.carried_over_days)} Tage</span>
              {(entitlementQuery.data.adjustment_days ?? 0) !== 0 && (
                <>
                  <span className="text-slate-500">Korrekturen</span>
                  <span className="text-right">
                    {entitlementQuery.data.adjustment_days > 0 ? '+' : ''}
                    {formatDays(entitlementQuery.data.adjustment_days)} Tage
                  </span>
                </>
              )}
              {entitlementQuery.data.expired_days > 0 && (
                <>
                  <span className="text-slate-500">
                    Verfallen{entitlementQuery.data.expiry_date ? ` nach ${formatDate(entitlementQuery.data.expiry_date)}` : ''}
                  </span>
                  <span className="text-right text-red-600">−{formatDays(entitlementQuery.data.expired_days)} Tage</span>
                </>
              )}
              <span className="text-slate-500">Genommen</span>
              <span className="text-right">{formatDays(entitlementQuery.data.used_days)} Tage</span>
              <span className="font-medium text-slate-900">Resturlaub</span>
              <span
                className={
                  entitlementQuery.data.remaining_days < 0
                    ? 'text-right font-semibold text-red-600'
                    : 'text-right font-semibold text-emerald-600'
                }
              >
                {formatDays(entitlementQuery.data.remaining_days)} Tage
              </span>
            </div>
            {entitlementQuery.data.expiring_days > 0 && entitlementQuery.data.expiry_date && (
              <p className="rounded-md bg-amber-50 p-2 text-xs text-amber-900">
                {formatDays(entitlementQuery.data.expiring_days)} Tage Übertrag verfallen, wenn sie nicht bis{' '}
                {formatDate(entitlementQuery.data.expiry_date)} genommen werden.
              </p>
            )}
            <LeaveAdjustments employeeId={employeeId} year={year} readOnly={readOnly} />
            {entitlementQuery.data.workdays_per_week !== null && (
              <p className="text-xs text-slate-500">
                Gezählt werden nur Arbeitstage laut Arbeitszeitmodell ({entitlementQuery.data.workdays_per_week} pro Woche).
              </p>
            )}
            {!entitlementQuery.data.entitled_manual && computed !== null && (
              <p className="text-xs text-slate-500">
                Berechnet aus {formatDays(entitlementQuery.data.annual_vacation_days)} Tagen Jahresurlaub (Vertrag bzw.
                Standard, 5-Tage-Woche) – je nach Einstellung anteilig für Teilzeit und für Ein- oder Austritt im Jahr.
              </p>
            )}
            {!entitlementQuery.data.entitled_manual && computed === null && (
              <p className="text-xs text-slate-500">Arbeitszeitmodell „Nach Aufwand“: Anspruch bitte eintragen.</p>
            )}
            {!readOnly && entitlementQuery.data.entitled_manual && computed !== null && computed !== entitlementQuery.data.entitled_days && (
              <div className="rounded-md bg-amber-50 p-2 text-xs text-amber-900">
                Berechnet wären {formatDays(computed)} Tage.{' '}
                <button
                  type="button"
                  className="font-medium underline"
                  onClick={() => void updateEntitlement.mutateAsync({ entitled_auto: true })}
                >
                  Wieder berechnen
                </button>
              </div>
            )}
            {!readOnly && (
              <Button variant="outline" size="sm" className="mt-2 self-start" onClick={() => setEditing(true)}>
                Bearbeiten
              </Button>
            )}
          </div>
        )}
        {entitlementQuery.data && editing && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="entitled_days">Anspruch (Tage)</Label>
                <Input
                  id="entitled_days"
                  type="number"
                  min={0}
                  step={0.5}
                  value={entitledDays}
                  onChange={(event) => setEntitledDays(Number(event.target.value) || 0)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="carried_over_days">Übertrag Vorjahr (Tage)</Label>
                <Input
                  id="carried_over_days"
                  type="number"
                  min={0}
                  step={0.5}
                  value={carriedOverDays}
                  onChange={(event) => setCarriedOverDays(Number(event.target.value) || 0)}
                />
              </div>
            </div>
            <p className="text-xs text-slate-500">
              Ein geänderter Anspruch gilt fest für {year}; ohne Änderung wird er weiter berechnet.
            </p>
            {entitlementQuery.data.entitled_manual && computed !== null && (
              <button
                type="button"
                className="self-start text-xs text-sky-700 underline"
                onClick={() => void updateEntitlement.mutateAsync({ entitled_auto: true }).then(() => setEditing(false))}
              >
                Anspruch wieder berechnen ({formatDays(computed)} Tage)
              </button>
            )}
            {!entitlementQuery.data.carried_over_auto && (
              <button
                type="button"
                className="self-start text-xs text-sky-700 underline"
                onClick={() =>
                  void updateEntitlement.mutateAsync({ carried_over_auto: true }).then(() => setEditing(false))
                }
              >
                Übertrag wieder automatisch berechnen (wenn in den Einstellungen aktiv)
              </button>
            )}
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
                Abbrechen
              </Button>
              <Button size="sm" disabled={updateEntitlement.isPending} onClick={handleSave}>
                {updateEntitlement.isPending ? 'Speichern…' : 'Speichern'}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/** Korrekturen am Urlaubskonto („Kontostand anpassen“): ± Tage mit Begründung, optional mit Verfall. */
function LeaveAdjustments({ employeeId, year, readOnly }: { employeeId: number; year: number; readOnly: boolean }) {
  const query = useLeaveAdjustmentsQuery(employeeId, year)
  const create = useCreateLeaveAdjustmentMutation(employeeId)
  const remove = useDeleteLeaveAdjustmentMutation(employeeId)
  const [open, setOpen] = useState(false)
  const [days, setDays] = useState('')
  const [expiresOn, setExpiresOn] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const adjustments = query.data ?? []
  if (readOnly && adjustments.length === 0) return null

  async function submit() {
    setError(null)
    const value = Number(days.replace(',', '.'))
    if (!value || Math.round(value * 2) !== value * 2) {
      setError('Bitte ganze oder halbe Tage angeben, z. B. 2 oder -0,5.')
      return
    }
    try {
      await create.mutateAsync({ year, days: value, expires_on: expiresOn || null, note: note.trim() })
      setDays('')
      setExpiresOn('')
      setNote('')
      setOpen(false)
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Angaben prüfen (Verfall nur bei Plus-Tagen).')
    }
  }

  return (
    <div className="flex flex-col gap-1.5 border-t border-slate-100 pt-2 text-sm">
      {adjustments.map((adjustment) => (
        <div key={adjustment.id} className="flex items-center justify-between gap-2">
          <span>
            <span className={adjustment.days < 0 ? 'text-red-600' : 'text-emerald-700'}>
              {adjustment.days > 0 ? '+' : ''}
              {formatDays(adjustment.days)} Tage
            </span>{' '}
            {adjustment.note}
            {adjustment.expires_on && <span className="text-slate-500"> (verfällt am {formatDate(adjustment.expires_on)})</span>}
          </span>
          {!readOnly && (
            <Button variant="ghost" size="sm" onClick={() => window.confirm('Korrektur löschen?') && remove.mutate(adjustment.id)}>
              Löschen
            </Button>
          )}
        </div>
      ))}
      {!readOnly && !open && (
        <button type="button" className="self-start text-xs text-sky-700 underline" onClick={() => setOpen(true)}>
          Urlaubskonto korrigieren (± Tage)
        </button>
      )}
      {!readOnly && open && (
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="adj_days">Tage (±)</Label>
            <Input id="adj_days" inputMode="decimal" placeholder="z. B. 2 oder -1" value={days} onChange={(e) => setDays(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="adj_expires">Verfällt am (optional)</Label>
            <Input id="adj_expires" type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="adj_reason">Begründung</Label>
            <Input id="adj_reason" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <p className="text-xs text-red-600 sm:col-span-3">{error}</p>}
          <div className="flex gap-2 sm:col-span-3">
            <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
              Abbrechen
            </Button>
            <Button size="sm" disabled={create.isPending || note.trim().length < 3} onClick={() => void submit()}>
              Buchen
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
