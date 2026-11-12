import { useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { useUpdateSettingsMutation, type Settings } from '../../api/queries/settings'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { SettingsCard } from './DefaultsSettingsCard'

function useSave() {
  const update = useUpdateSettingsMutation()
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  async function save(payload: Parameters<typeof update.mutateAsync>[0]) {
    setError(null)
    setMessage(null)
    try {
      await update.mutateAsync(payload)
      setMessage('Gespeichert.')
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Eingaben prüfen.')
    }
  }
  return { save, message, error, pending: update.isPending }
}

/** Einstellungen → „Stempeln“: Zeiten selbst eintragen (Stundenzettel in „Mein Bereich“). Nur je Firma –
 * bewusst ohne Abweichung je Arbeitszeitmodell oder Mitarbeiter. */
export function TimeSheetSettingsCard({ settings }: { settings: Settings }) {
  const { save, message, error, pending } = useSave()
  const [days, setDays] = useState(String(settings.self_time_entry_backdate_days ?? 7))
  useEffect(() => setDays(String(settings.self_time_entry_backdate_days ?? 7)), [settings.self_time_entry_backdate_days])
  const enabled = settings.self_time_entry_enabled ?? false
  const daysValid = /^\d+$/.test(days) && Number(days) <= 62

  return (
    <SettingsCard
      title="Zeiten selbst eintragen (Stundenzettel)"
      description="Mitarbeiter mit eigenem Login tragen in „Mein Bereich“ → „Zeiterfassung“ ihre Arbeitszeiten selbst ein – je Tag mehrere Zeiten, auch mit Pausen und für Tage ohne Stempelung. Überschneidungen mit vorhandenen Zeiten, Tage in der Zukunft und abgeschlossene Monate sind ausgeschlossen."
      message={message}
      error={error}
    >
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={enabled}
          disabled={pending}
          onChange={(e) => void save({ self_time_entry_enabled: e.target.checked })}
        />
        Zeiten selbst eintragen erlauben
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.self_time_entry_approval ?? true}
          disabled={pending || !enabled}
          onChange={(e) => void save({ self_time_entry_approval: e.target.checked })}
        />
        <span>
          Genehmigung nötig
          <span className="block text-xs text-slate-500">
            An: Einträge erscheinen unter „Zu klären“ → „Korrekturanträge“ und zählen erst nach „Übernehmen“. Aus: Sie
            zählen sofort, sind als „Selbst eingetragen“ gekennzeichnet und stehen im Audit-Protokoll; Mitarbeiter
            können sie im erlaubten Zeitraum selbst wieder löschen.
          </span>
        </span>
      </label>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span>Rückwirkend eintragen bis</span>
        <Input
          type="number"
          min={0}
          max={62}
          aria-label="Rückwirkend eintragen bis Tage"
          className="w-20"
          value={days}
          disabled={!enabled}
          onChange={(e) => setDays(e.target.value)}
        />
        <span className="text-slate-500">Tage (0 = nur heute)</span>
        <Button
          size="sm"
          variant="outline"
          disabled={!enabled || !daysValid || days === String(settings.self_time_entry_backdate_days)}
          onClick={() => void save({ self_time_entry_backdate_days: Number(days) })}
        >
          Übernehmen
        </Button>
      </div>
    </SettingsCard>
  )
}
