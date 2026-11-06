import { usePlanQuery } from '../../api/queries/plan'

/** Hinweis in der Mitarbeiterliste, wenn der kostenlose Tarif (fast) ausgeschöpft ist. */
export function PlanNotice() {
  const plan = usePlanQuery().data
  if (!plan || plan.limit == null || plan.remaining == null || plan.remaining > 1) return null
  const full = plan.remaining === 0
  return (
    <div
      className={`rounded-md border p-3 text-sm ${full ? 'border-amber-300 bg-amber-50 text-amber-900' : 'border-sky-200 bg-sky-50 text-sky-900'}`}
    >
      Kostenloser Tarif: {plan.active_employees} von {plan.limit} aktiven Mitarbeitern.{' '}
      {full
        ? 'Weitere Mitarbeiter lassen sich nur mit Abo aktivieren – oder einen anderen Mitarbeiter deaktivieren.'
        : 'Noch ein Mitarbeiter frei.'}
    </div>
  )
}

/** Tarif-Karte für Einstellungen → „Tarif & Konto“. */
export function PlanCard() {
  const plan = usePlanQuery().data
  if (!plan) return null
  const share = plan.limit ? Math.min(plan.active_employees / plan.limit, 1) : 0
  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div>
        <p className="text-sm font-medium text-slate-800">Tarif</p>
        <p className="text-sm text-slate-500">
          {plan.plan === 'FREE' &&
            `Kostenlos für bis zu ${plan.limit} aktive Mitarbeiter. Ab ${(plan.limit ?? 0) + 1} aktiven Mitarbeitern kostet jeder aktive Mitarbeiter 1 € im Monat (z. B. ${(plan.limit ?? 0) + 1} Mitarbeiter = ${(plan.limit ?? 0) + 1} €) – das Abo lässt sich bald direkt hier abschließen.`}
          {plan.plan === 'PAID' && 'Abo: unbegrenzt viele Mitarbeiter, 1 € je aktivem Mitarbeiter und Monat.'}
          {plan.plan === 'UNLIMITED' && 'Unbegrenzt – ohne Mitarbeitergrenze.'}
        </p>
      </div>
      <p className="text-sm text-slate-800">
        <span className="font-semibold">{plan.active_employees}</span>
        {plan.limit != null ? ` von ${plan.limit}` : ''} aktive Mitarbeiter
      </p>
      {plan.limit != null && (
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-label="Auslastung des Tarifs"
          aria-valuenow={plan.active_employees}
          aria-valuemax={plan.limit}
        >
          <div
            className={`h-full ${share >= 1 ? 'bg-amber-500' : 'bg-emerald-500'}`}
            style={{ width: `${Math.round(share * 100)}%` }}
          />
        </div>
      )}
    </div>
  )
}
