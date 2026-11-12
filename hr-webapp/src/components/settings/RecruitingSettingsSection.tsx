import { useState } from 'react'
import { ApiError } from '../../api/client'
import { useUpdateSettingsMutation, type Settings } from '../../api/queries/settings'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { SettingsCard, SettingsToggle } from './DefaultsSettingsCard'

function saveError(error: unknown): string | null {
  if (!error) return null
  return error instanceof ApiError && error.status !== 422 ? error.message : 'Speichern fehlgeschlagen – bitte Eingaben prüfen.'
}

/** Einstellungen → „Recruiting“ (Admin): Schalter, Datenschutzhinweise für Bewerber, Löschfristen. */
export function RecruitingSettingsSection({ settings }: { settings: Settings }) {
  const update = useUpdateSettingsMutation()
  const [privacyText, setPrivacyText] = useState(settings.recruiting_privacy_text ?? '')
  const [privacyUrl, setPrivacyUrl] = useState(settings.recruiting_privacy_url ?? '')
  const [retention, setRetention] = useState(String(settings.recruiting_retention_months ?? 6))
  const [pool, setPool] = useState(String(settings.recruiting_talent_pool_months ?? 12))
  const [message, setMessage] = useState<string | null>(null)
  const error = saveError(update.error)

  async function savePrivacy() {
    setMessage(null)
    await update.mutateAsync({ recruiting_privacy_text: privacyText, recruiting_privacy_url: privacyUrl.trim() })
    setMessage('Gespeichert.')
  }

  async function saveRetention() {
    setMessage(null)
    await update.mutateAsync({
      recruiting_retention_months: Number(retention),
      recruiting_talent_pool_months: Number(pool),
    })
    setMessage('Gespeichert.')
  }

  return (
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
      <div className="flex flex-col gap-4">
        {error && <p className="text-sm text-red-600">{error}</p>}
        {message && !error && <p className="text-sm text-emerald-700">{message}</p>}
        <SettingsToggle
          checked={settings.recruiting_enabled ?? false}
          disabled={update.isPending}
          onChange={(checked) => update.mutate({ recruiting_enabled: checked })}
          title="Recruiting einschalten"
        >
          Menüpunkt „Recruiting“ mit Stellen und Bewerbungen sowie die öffentliche Karriereseite unter /karriere. Ausgeschaltet
          sind Menüpunkt und Karriereseite nicht erreichbar; gespeicherte Bewerbungen bleiben erhalten und werden weiter nach
          Frist gelöscht.
        </SettingsToggle>
        <SettingsCard
          title="Löschfristen"
          description="Abgelehnte und zurückgezogene Bewerbungen werden nach dieser Frist ab dem Abschluss automatisch gelöscht (Daten, Notizen, Bewertungen, Anhänge). Übrig bleibt nur eine anonyme Zählung je Stelle."
        >
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              Frist in Monaten
              <Input
                type="number"
                min={1}
                max={36}
                className="w-28"
                aria-label="Löschfrist in Monaten"
                value={retention}
                onChange={(e) => setRetention(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              Talentpool in Monaten
              <Input
                type="number"
                min={1}
                max={60}
                className="w-28"
                aria-label="Frist im Talentpool in Monaten"
                value={pool}
                onChange={(e) => setPool(e.target.value)}
              />
            </label>
            <Button size="sm" disabled={update.isPending} onClick={() => void saveRetention().catch(() => undefined)}>
              Fristen speichern
            </Button>
          </div>
        </SettingsCard>
      </div>
      <SettingsCard
        title="Datenschutzhinweise für Bewerber"
        description="Erscheinen über dem Bewerbungsformular; Bewerber müssen die Kenntnisnahme bestätigen. Text und/oder Link (https://)."
      >
        <textarea
          aria-label="Datenschutzhinweise (Text)"
          rows={6}
          maxLength={5000}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          value={privacyText}
          onChange={(e) => setPrivacyText(e.target.value)}
        />
        <Input
          aria-label="Link zu den Datenschutzhinweisen"
          placeholder="https://example.com/datenschutz-bewerber"
          maxLength={500}
          value={privacyUrl}
          onChange={(e) => setPrivacyUrl(e.target.value)}
        />
        <div>
          <Button size="sm" disabled={update.isPending} onClick={() => void savePrivacy().catch(() => undefined)}>
            Hinweise speichern
          </Button>
        </div>
      </SettingsCard>
    </div>
  )
}
