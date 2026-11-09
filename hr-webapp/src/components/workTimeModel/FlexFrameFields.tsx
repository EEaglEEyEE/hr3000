/** Gleitzeit-Rahmen einer Fassung bzw. eines Arbeitszeitmodells: wie in den Einstellungen, eigener Rahmen
 *  (jeden Tag gleich oder je Wochentag) oder kein Rahmen. */
import {
  coreTimeDaysFromApi,
  coreTimeDaysValid,
  DayWindowsEditor,
  describeDayWindows,
  initialCoreTimeDays,
  type DayWindow,
} from '../coreTime/CoreTimeDaysEditor'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

export type FlexFrameMode = 'TENANT' | 'CUSTOM' | 'NONE'

export type FlexFrameValue = { mode: FlexFrameMode; start: string; end: string; days: DayWindow[] | null }

const DEFAULT_WINDOW = { start: '07:00', end: '19:00' }

export const DEFAULT_FLEX_FRAME: FlexFrameValue = { mode: 'TENANT', ...DEFAULT_WINDOW, days: null }

type ApiFlexFrame = {
  flex_frame_mode?: string | null
  flex_frame_start?: string | null
  flex_frame_end?: string | null
  flex_frame_days?: ({ start: string; end: string } | null)[] | null
}

export function flexFrameFromApi(source: ApiFlexFrame): FlexFrameValue {
  return {
    mode: (source.flex_frame_mode as FlexFrameMode | null | undefined) ?? 'TENANT',
    start: source.flex_frame_start?.slice(0, 5) || DEFAULT_WINDOW.start,
    end: source.flex_frame_end?.slice(0, 5) || DEFAULT_WINDOW.end,
    days: coreTimeDaysFromApi(source.flex_frame_days),
  }
}

export function flexFrameValid(value: FlexFrameValue): boolean {
  if (value.mode !== 'CUSTOM') return true
  if (value.days) return coreTimeDaysValid(value.days)
  return value.start !== '' && value.end !== '' && value.start < value.end
}

export function flexFramePayload(value: FlexFrameValue) {
  if (value.mode !== 'CUSTOM') return { flex_frame_mode: value.mode, flex_frame_start: null, flex_frame_end: null, flex_frame_days: null }
  return value.days
    ? { flex_frame_mode: value.mode, flex_frame_start: null, flex_frame_end: null, flex_frame_days: value.days }
    : { flex_frame_mode: value.mode, flex_frame_start: value.start, flex_frame_end: value.end, flex_frame_days: null }
}

/** Kurzbeschreibung, z. B. „07:00–19:00“ oder „je Wochentag (Mo–Do 07:00–19:00, Fr 07:00–14:00, Sa–So keiner)“
 *  (leer = wie in den Einstellungen). */
export function flexFrameText(source: ApiFlexFrame): string {
  if (source.flex_frame_mode === 'NONE') return 'keiner'
  if (source.flex_frame_mode !== 'CUSTOM') return ''
  const days = coreTimeDaysFromApi(source.flex_frame_days)
  if (days) return `je Wochentag (${describeDayWindows(days, 'keiner')})`
  if (source.flex_frame_start && source.flex_frame_end) {
    return `${source.flex_frame_start.slice(0, 5)}–${source.flex_frame_end.slice(0, 5)}`
  }
  return ''
}

export function FlexFrameFields({ value, onChange }: { value: FlexFrameValue; onChange: (value: FlexFrameValue) => void }) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">Gleitzeit-Rahmen</legend>
      <div className="flex flex-wrap gap-2 text-sm">
        {(
          [
            ['TENANT', 'Wie Einstellungen'],
            ['CUSTOM', 'Eigener Rahmen'],
            ['NONE', 'Kein Rahmen'],
          ] as const
        ).map(([kind, label]) => (
          <Button
            key={kind}
            type="button"
            size="sm"
            variant={value.mode === kind ? 'default' : 'outline'}
            aria-pressed={value.mode === kind}
            onClick={() => onChange({ ...value, mode: kind })}
          >
            {label}
          </Button>
        ))}
      </div>
      {value.mode === 'CUSTOM' && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value.days !== null}
            onChange={(e) =>
              onChange({ ...value, days: e.target.checked ? initialCoreTimeDays(value.start, value.end, DEFAULT_WINDOW) : null })
            }
          />
          Rahmen je Wochentag unterschiedlich
        </label>
      )}
      {value.mode === 'CUSTOM' && value.days && (
        <DayWindowsEditor
          days={value.days}
          onChange={(days) => onChange({ ...value, days })}
          name="Rahmen"
          ariaPrefix="Rahmen "
          noneLabel="kein Rahmen"
          defaultWindow={DEFAULT_WINDOW}
        />
      )}
      {value.mode === 'CUSTOM' && !value.days && (
        <div className="flex items-center gap-2">
          <Input
            aria-label="Rahmen von"
            type="time"
            className="w-32"
            value={value.start}
            onChange={(event) => onChange({ ...value, start: event.target.value })}
          />
          <span className="text-sm text-slate-600">bis</span>
          <Input
            aria-label="Rahmen bis"
            type="time"
            className="w-32"
            value={value.end}
            onChange={(event) => onChange({ ...value, end: event.target.value })}
          />
        </div>
      )}
      <p className="text-sm text-slate-500">
        Kommen oder Gehen außerhalb des Rahmens erscheint unter „Zu klären“ – nur ein Hinweis, an den Stunden ändert sich
        nichts. An Tagen ohne Rahmen wird nichts geprüft. Schichten mit Uhrzeiten haben Vorrang.
      </p>
    </fieldset>
  )
}
