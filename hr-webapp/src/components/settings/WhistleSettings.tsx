import { useState } from 'react'
import { ApiError } from '../../api/client'
import { useUpdateSettingsMutation, type Settings } from '../../api/queries/settings'
import {
  useAppointWhistleOfficerMutation,
  useDismissWhistleOfficerMutation,
  useWhistleOfficersQuery,
} from '../../api/queries/whistle'
import { Button } from '../ui/button'
import { SettingsCard, SettingsToggle } from './DefaultsSettingsCard'

function errorText(error: unknown): string | null {
  if (!error) return null
  return error instanceof ApiError ? error.message : 'Speichern fehlgeschlagen.'
}

/** Einstellungen → Hinweisgebersystem: Schalter, Link zur Meldeseite und Meldestellen-Beauftragte. */
export function WhistleSettings({ settings }: { settings: Settings }) {
  const update = useUpdateSettingsMutation()
  const link = `${window.location.origin}/hinweis`
  return (
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
      <div className="flex flex-col gap-4">
        <SettingsToggle
          checked={settings.whistleblowing_enabled}
          disabled={update.isPending}
          onChange={(checked) => update.mutate({ whistleblowing_enabled: checked })}
          title="Hinweisgebersystem"
        >
          Öffentliche Seite, über die Beschäftigte und Dritte ohne Anmeldung einen Hinweis abgeben können – auf Wunsch
          anonym. Die Hinweise sehen nur die unten benannten Meldestellen-Beauftragten, nicht automatisch Admins oder HR.
          Für die rechtliche Ausgestaltung der Meldestelle ist die Firma selbst verantwortlich.
        </SettingsToggle>
        {update.error && <p className="text-sm text-red-600">{errorText(update.error)}</p>}
        <SettingsCard
          title="Link zur Meldeseite"
          description="Diesen Link intern bekannt geben (z. B. Intranet, Aushang). „Mein Bereich“ zeigt ihn allen Mitarbeitern."
        >
          <code className="break-all rounded bg-slate-100 px-2 py-1 text-sm text-slate-800">{link}</code>
          {!settings.whistleblowing_enabled && (
            <p className="text-sm text-slate-500">Der Link funktioniert erst, wenn das Hinweisgebersystem eingeschaltet ist.</p>
          )}
        </SettingsCard>
      </div>
      <OfficersCard />
    </div>
  )
}

function OfficersCard() {
  const officersQuery = useWhistleOfficersQuery()
  const appoint = useAppointWhistleOfficerMutation()
  const dismiss = useDismissWhistleOfficerMutation()
  const [selected, setSelected] = useState('')
  const data = officersQuery.data
  const error = errorText(appoint.error) ?? errorText(dismiss.error)

  return (
    <SettingsCard
      title="Meldestellen-Beauftragte"
      description="Nur diese Personen sehen und bearbeiten Hinweise (Menüpunkt „Hinweise“). Benennen und Abberufen steht im Audit-Protokoll. Ohne Beauftragte nimmt die Meldeseite keine Hinweise an."
      error={error}
    >
      {officersQuery.isLoading && <p className="text-sm text-slate-500">Lädt…</p>}
      {data && (
        <>
          {data.officers.length === 0 ? (
            <p className="text-sm text-amber-700">Noch niemand benannt.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {data.officers.map((officer) => (
                <li key={officer.account_id} className="flex items-center justify-between gap-2 text-sm">
                  <span>
                    {officer.name}
                    {officer.email && officer.email !== officer.name && <span className="text-slate-500"> · {officer.email}</span>}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={dismiss.isPending}
                    onClick={() => dismiss.mutate(officer.account_id)}
                  >
                    Abberufen
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Konto benennen"
              className="h-9 min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-2 text-sm"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Konto wählen…</option>
              {data.candidates.map((candidate) => (
                <option key={candidate.account_id} value={candidate.account_id}>
                  {candidate.name}
                  {candidate.email && candidate.email !== candidate.name ? ` (${candidate.email})` : ''}
                </option>
              ))}
            </select>
            <Button
              type="button"
              disabled={!selected || appoint.isPending}
              onClick={() => appoint.mutate(Number(selected), { onSuccess: () => setSelected('') })}
            >
              Benennen
            </Button>
          </div>
        </>
      )}
    </SettingsCard>
  )
}
