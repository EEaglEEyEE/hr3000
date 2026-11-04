import { useEffect, useState } from 'react'
import {
  useLeaveEntitlementQuery,
  useUpdateLeaveEntitlementMutation,
} from '../../api/queries/leaveEntitlements'
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
    // Übertrag nur mitschicken, wenn geändert – sonst würde ein automatischer Übertrag festgeschrieben.
    const carriedChanged = carriedOverDays !== entitlementQuery.data?.carried_over_days
    await updateEntitlement.mutateAsync({
      entitled_days: entitledDays,
      ...(carriedChanged ? { carried_over_days: carriedOverDays } : {}),
    })
    setEditing(false)
  }

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
              <span className="text-slate-500">Anspruch</span>
              <span className="text-right">{formatDays(entitlementQuery.data.entitled_days)} Tage</span>
              <span className="text-slate-500">
                Übertrag Vorjahr{entitlementQuery.data.carried_over_auto ? ' (automatisch)' : ''}
              </span>
              <span className="text-right">{formatDays(entitlementQuery.data.carried_over_days)} Tage</span>
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
            {entitlementQuery.data.workdays_per_week !== null && (
              <p className="text-xs text-slate-500">
                Gezählt werden nur Arbeitstage laut Arbeitszeitmodell ({entitlementQuery.data.workdays_per_week} pro Woche).
              </p>
            )}
            {!readOnly &&
              entitlementQuery.data.suggested_entitled_days !== null &&
              entitlementQuery.data.suggested_entitled_days !== entitlementQuery.data.entitled_days && (
                <div className="rounded-md bg-amber-50 p-2 text-xs text-amber-900">
                  Anteiliger Anspruch laut Arbeitszeitmodell: {entitlementQuery.data.suggested_entitled_days} Tage.{' '}
                  <button
                    type="button"
                    className="font-medium underline"
                    onClick={() =>
                      void updateEntitlement.mutateAsync({ entitled_days: entitlementQuery.data!.suggested_entitled_days! })
                    }
                  >
                    Übernehmen
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
