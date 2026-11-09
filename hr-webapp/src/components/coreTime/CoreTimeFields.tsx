/** Kernarbeitszeit/Pünktlichkeit einer Fassung des Arbeitszeitmodells: wie in den Einstellungen,
 *  eigene Kernzeit (gleich oder je Wochentag) oder keine Prüfung. */
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import {
  CoreTimeDaysEditor,
  coreTimeDaysFromApi,
  coreTimeDaysValid,
  initialCoreTimeDays,
  type CoreTimeDay,
} from './CoreTimeDaysEditor'

export type CoreTimeMode = 'TENANT' | 'CUSTOM' | 'NONE'

export type CoreTimeValue = { mode: CoreTimeMode; start: string; end: string; days: CoreTimeDay[] | null }

export const DEFAULT_CORE_TIME: CoreTimeValue = { mode: 'TENANT', start: '', end: '', days: null }

type ApiCoreTime = {
  core_time_mode?: string | null
  core_time_start?: string | null
  core_time_end?: string | null
  core_time_days?: ({ start: string; end: string } | null)[] | null
}

export function coreTimeFromApi(source: ApiCoreTime): CoreTimeValue {
  return {
    mode: (source.core_time_mode as CoreTimeMode | null | undefined) ?? 'TENANT',
    start: source.core_time_start?.slice(0, 5) ?? '',
    end: source.core_time_end?.slice(0, 5) ?? '',
    days: coreTimeDaysFromApi(source.core_time_days),
  }
}

export function coreTimeValid(value: CoreTimeValue): boolean {
  if (value.mode !== 'CUSTOM') return true
  if (value.days) return coreTimeDaysValid(value.days)
  return value.start !== '' && value.end !== '' && value.start < value.end
}

export function coreTimePayload(value: CoreTimeValue) {
  if (value.mode !== 'CUSTOM') return { core_time_mode: value.mode }
  return value.days
    ? { core_time_mode: value.mode, core_time_days: value.days }
    : { core_time_mode: value.mode, core_time_start: value.start, core_time_end: value.end, core_time_days: null }
}

/** Kurzbeschreibung, z. B. „eigene Kernzeit 10:00–14:00“ (leer = wie Einstellungen). */
export function coreTimeLabel(source: ApiCoreTime): string {
  const value = coreTimeFromApi(source)
  if (value.mode === 'NONE') return 'keine Pünktlichkeitsprüfung'
  if (value.mode !== 'CUSTOM') return ''
  if (value.days) return 'eigene Kernzeit je Wochentag'
  return `eigene Kernzeit ${value.start}–${value.end}`
}

export function CoreTimeFields({ value, onChange }: { value: CoreTimeValue; onChange: (value: CoreTimeValue) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="core_time_mode">Kernarbeitszeit / Pünktlichkeit</Label>
      <select
        id="core_time_mode"
        className="h-9 w-72 max-w-full rounded-md border border-slate-300 bg-white px-2 text-sm"
        value={value.mode}
        onChange={(event) => onChange({ ...value, mode: event.target.value as CoreTimeMode })}
      >
        <option value="TENANT">Wie in den Einstellungen</option>
        <option value="CUSTOM">Eigene Kernzeit</option>
        <option value="NONE">Keine Prüfung (z. B. Außendienst)</option>
      </select>
      {value.mode === 'CUSTOM' && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value.days !== null}
            onChange={(e) => onChange({ ...value, days: e.target.checked ? initialCoreTimeDays(value.start, value.end) : null })}
          />
          Je Wochentag unterschiedlich
        </label>
      )}
      {value.mode === 'CUSTOM' && value.days && (
        <CoreTimeDaysEditor days={value.days} onChange={(days) => onChange({ ...value, days })} />
      )}
      {value.mode === 'CUSTOM' && !value.days && (
        <div className="flex items-center gap-2">
          <Input
            type="time"
            aria-label="Eigene Kernzeit von"
            className="w-28"
            value={value.start}
            onChange={(event) => onChange({ ...value, start: event.target.value })}
          />
          <span className="text-sm text-slate-500">bis</span>
          <Input
            type="time"
            aria-label="Eigene Kernzeit bis"
            className="w-28"
            value={value.end}
            onChange={(event) => onChange({ ...value, end: event.target.value })}
          />
        </div>
      )}
      <p className="text-sm text-slate-500">
        Nur Hinweise „zu spät“/„zu früh“ unter „Zu klären“ – an den Stunden ändert sich nichts. Feste Uhrzeiten einer
        Schichtvorlage gehen der Kernzeit vor.
      </p>
    </div>
  )
}
