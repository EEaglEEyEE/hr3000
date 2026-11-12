import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { useLocationsQuery } from '../../api/queries/locations'
import { useUpdateSettingsMutation, type Settings } from '../../api/queries/settings'
import { SettingsToggle } from './DefaultsSettingsCard'

type Mode = Settings['punch_location_mode']

const MODES: { value: Mode; label: string; hint: string }[] = [
  {
    value: 'RECORD',
    label: 'Nur vermerken',
    hint: 'Stempeln ist immer möglich. Die Buchung bekommt den Vermerk „innerhalb“, „außerhalb“ oder „Standort unbekannt“.',
  },
  {
    value: 'BLOCK',
    label: 'Außerhalb nicht erlauben',
    hint: 'Außerhalb der Standorte oder ohne Standortfreigabe im Browser wird das Stempeln mit einer Meldung abgelehnt.',
  },
]

/** Einstellungen → Stempeln: Standort beim Stempeln im Web-Login prüfen (Schalter und Modus). */
export function PunchLocationSettings({ settings }: { settings: Settings }) {
  const update = useUpdateSettingsMutation()
  const locationsQuery = useLocationsQuery(settings.punch_location_check_enabled)
  const enabled = settings.punch_location_check_enabled
  const withCircle = (locationsQuery.data ?? []).filter((location) => location.geo_radius_m != null).length
  return (
    <div className="flex flex-col gap-3">
      <SettingsToggle
        checked={enabled}
        disabled={update.isPending}
        onChange={(checked) => update.mutate({ punch_location_check_enabled: checked })}
        title="Standort beim Stempeln prüfen (Web-Login)"
      >
        Beim Stempeln im Web-Login fragt der Browser einmalig nach dem Standort. Der Server prüft, ob die Position in
        einem der Kreise liegt, die unter „Standorte“ eingetragen sind (alle Standorte der Firma zählen). Gespeichert wird
        nur das Ergebnis an der Buchung – keine Koordinaten. Tablets und Nachträge durch HR sind nicht betroffen.
      </SettingsToggle>
      {enabled && (
        <div role="radiogroup" aria-label="Wenn die Position außerhalb liegt" className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4">
          <p className="text-sm font-medium text-slate-800">Wenn die Position außerhalb liegt</p>
          {MODES.map((mode) => (
            <label key={mode.value} className="flex items-start gap-3">
              <input
                type="radio"
                name="punch_location_mode"
                className="mt-1 h-4 w-4 shrink-0"
                checked={settings.punch_location_mode === mode.value}
                disabled={update.isPending}
                onChange={() => update.mutate({ punch_location_mode: mode.value })}
              />
              <span>
                <span className="block text-sm font-medium text-slate-800">{mode.label}</span>
                <span className="block text-sm text-slate-500">{mode.hint}</span>
              </span>
            </label>
          ))}
          {locationsQuery.data && withCircle === 0 && (
            <p className="text-sm text-amber-700">
              Noch kein Standort hat einen Kreis – solange wird nicht geprüft. Kreise unter{' '}
              <Link to="/einstellungen/standorte" className="underline">
                Standorte
              </Link>{' '}
              eintragen.
            </p>
          )}
        </div>
      )}
      {update.error && (
        <p className="text-sm text-red-600">{update.error instanceof ApiError ? update.error.message : 'Speichern fehlgeschlagen.'}</p>
      )}
    </div>
  )
}
