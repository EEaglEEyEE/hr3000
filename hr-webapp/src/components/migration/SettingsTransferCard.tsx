/** Einstellungen als Datei exportieren und (z. B. in einer neuen Firma) importieren – mit Vorschau. */
import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Download, Upload } from 'lucide-react'
import { apiClient, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { SettingsCard } from '../settings/DefaultsSettingsCard'
import { Button } from '../ui/button'

type SettingsFile = components['schemas']['TenantSettingsFile']
type ImportResult = components['schemas']['SettingsImportResult']

export function SettingsTransferCard() {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<SettingsFile | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<void>) {
    setError(null)
    setBusy(true)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehlgeschlagen.')
    } finally {
      setBusy(false)
    }
  }

  async function exportFile() {
    const data = unwrap(await apiClient.GET('/migration/settings-export'))
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'hr3000-einstellungen.json'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  async function preview(selected: File) {
    let parsed: SettingsFile
    try {
      parsed = JSON.parse(await selected.text()) as SettingsFile
    } catch {
      throw new Error('Die Datei ist keine gültige Einstellungs-Datei (JSON).')
    }
    const response = unwrap(await apiClient.POST('/migration/settings-import', { body: parsed, params: { query: { apply: false } } }))
    setFile(parsed)
    setResult(response)
  }

  async function apply() {
    if (!file) return
    const response = unwrap(await apiClient.POST('/migration/settings-import', { body: file, params: { query: { apply: true } } }))
    setResult(response)
    setFile(null)
    if (inputRef.current) inputRef.current.value = ''
    for (const key of ['settings', 'break-rules', 'absence-types', 'surcharge-rules', 'features']) {
      void queryClient.invalidateQueries({ queryKey: [key] })
    }
  }

  return (
    <SettingsCard
      title="Einstellungen übertragen"
      description="Für den Umstieg oder eine zweite Firma: fachliche Einstellungen, Pausenregeln, Abwesenheitsarten und Zuschläge als Datei. Mailserver, Tablet-PIN, „Gleitzeitkonten führen ab“ und die DATEV-Nummern bleiben außen vor. Beim Import werden Einstellungen überschrieben, Regeln und Arten nur ergänzt."
      error={error}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => void run(exportFile)}>
          <Download className="h-4 w-4" />
          Exportieren
        </Button>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-50">
          <Upload className="h-4 w-4" />
          Datei importieren
          <input
            ref={inputRef}
            type="file"
            accept=".json,application/json"
            aria-label="Einstellungs-Datei"
            className="sr-only"
            onChange={(e) => {
              const selected = e.target.files?.[0]
              setResult(null)
              if (selected) void run(() => preview(selected))
            }}
          />
        </label>
      </div>
      {result && (
        <div className="flex flex-col gap-2 text-sm">
          <p className={result.applied ? 'text-emerald-700' : 'text-slate-700'}>
            {result.applied
              ? `Übernommen: ${result.changes.length} Änderung(en).`
              : result.changes.length > 0
                ? `Vorschau: ${result.changes.length} Änderung(en).`
                : 'Vorschau: Alles ist schon so eingestellt.'}
          </p>
          {result.changes.length > 0 && (
            <ul className="ml-4 list-disc text-slate-600">
              {result.changes.map((change) => (
                <li key={change}>{change}</li>
              ))}
            </ul>
          )}
          {result.skipped.length > 0 && (
            <ul className="ml-4 list-disc text-amber-800">
              {result.skipped.map((entry) => (
                <li key={entry}>{entry}</li>
              ))}
            </ul>
          )}
          {!result.applied && file && result.changes.length > 0 && (
            <div>
              <Button size="sm" disabled={busy} onClick={() => void run(apply)}>
                Übernehmen
              </Button>
            </div>
          )}
        </div>
      )}
    </SettingsCard>
  )
}
