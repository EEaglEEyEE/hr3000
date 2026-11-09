import { useId } from 'react'
import type { Settings } from '../../api/queries/settings'

type TwoFactorRole = Settings['two_factor_roles'][number]

const GROUPS: { value: TwoFactorRole; label: string }[] = [
  { value: 'ADMIN', label: 'Admin' },
  { value: 'HR', label: 'HR' },
  { value: 'SUPERVISOR', label: 'Führungskräfte' },
  { value: 'EMPLOYEE', label: 'Mitarbeiter ohne Rolle' },
]

/** Pflicht zur Zwei-Faktor-Anmeldung je Gruppe („Alle“ kreuzt alle Gruppen an). */
export function TwoFactorPolicyCard({
  roles,
  disabled,
  onChange,
}: {
  roles: TwoFactorRole[]
  disabled?: boolean
  onChange: (roles: TwoFactorRole[]) => void
}) {
  const titleId = useId()
  const selected = new Set(roles)
  const all = GROUPS.every((group) => selected.has(group.value))

  function toggle(value: TwoFactorRole, checked: boolean) {
    onChange(GROUPS.map((group) => group.value).filter((v) => (v === value ? checked : selected.has(v))))
  }

  return (
    <div role="group" aria-labelledby={titleId} className="rounded-md border border-slate-200 bg-white p-4">
      <p id={titleId} className="text-sm font-medium text-slate-800">
        Zwei-Faktor-Anmeldung verpflichtend für
      </p>
      <p className="text-sm text-slate-500">
        Wer zu einer angekreuzten Gruppe gehört, richtet bei der nächsten Anmeldung eine Authenticator-App ein und gibt
        danach bei jeder Anmeldung zusätzlich einen Code ein. Alle anderen können sie freiwillig nutzen. Das Stempeln am
        Tablet bleibt unverändert.
      </p>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
        <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300"
            checked={all}
            disabled={disabled}
            onChange={(event) => onChange(event.target.checked ? GROUPS.map((group) => group.value) : [])}
          />
          Alle
        </label>
        {GROUPS.map((group) => (
          <label key={group.value} className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={selected.has(group.value)}
              disabled={disabled}
              onChange={(event) => toggle(group.value, event.target.checked)}
            />
            {group.label}
          </label>
        ))}
      </div>
    </div>
  )
}
