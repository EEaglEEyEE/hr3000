/** Texte und Hilfen zum Arbeitszeitmodell – gemeinsam für den Reiter am Mitarbeiter und die
 * Arbeitszeitmodelle. */
import type { WorkTimeModelVersion } from '../../api/queries/workTimeModel'
import { formatDate } from '../../lib/format'
import { coreTimeLabel } from '../coreTime/CoreTimeFields'
import { flexFrameText } from './FlexFrameFields'

export const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

/** Angaben einer Fassung, mit denen das Formular vorbelegt wird (Fassung, aktuelles Modell oder Modell). */
export type ModelSource = Omit<WorkTimeModelVersion, 'id' | 'valid_from' | 'valid_to'>

export function hhmm(value: string | null | undefined): string {
  return value ? value.slice(0, 5) : ''
}

/** Pause einer Fassung als Text, z. B. ", Pause 30 Min." (leer = Pausenregeln). */
export function breakLabel(source: {
  break_minutes?: number | null
  break_after_minutes?: number
  break_start?: string | null
  break_end?: string | null
  break_windows?: { start: string; end: string }[] | null
}): string {
  if (source.break_minutes) {
    const after = source.break_after_minutes ? ` ab ${formatHours(source.break_after_minutes)} Std.` : ''
    return `, Pause ${source.break_minutes} Min.${after}`
  }
  if (source.break_windows && source.break_windows.length > 1) {
    return `, Pause ${source.break_windows.map((w) => `${hhmm(w.start)}–${hhmm(w.end)}`).join(', ')}`
  }
  if (source.break_start && source.break_end) return `, Pause ${hhmm(source.break_start)}–${hhmm(source.break_end)}`
  return ''
}

/** Schichtvorlage einer Fassung als Text, z. B. ", Schicht „Früh“ 06:00–14:30". */
export function shiftLabel(source: { shift_template_name?: string | null; shift_start?: string | null; shift_end?: string | null }): string {
  if (!source.shift_template_name) return ''
  const times = source.shift_start && source.shift_end ? ` ${hhmm(source.shift_start)}–${hhmm(source.shift_end)}` : ''
  return `, Schicht „${source.shift_template_name}“${times}`
}

export function formatHours(minutes: number): string {
  return (minutes / 60).toLocaleString('de-DE', { maximumFractionDigits: 2 })
}

export function formatRange(version: { valid_from: string; valid_to?: string | null }): string {
  return `${formatDate(version.valid_from)} – ${version.valid_to ? formatDate(version.valid_to) : 'heute'}`
}

/** Gleitzeit-Rahmen einer Fassung bzw. eines Modells (leer = wie in den Einstellungen). */
export function flexFrameLabel(
  source: Pick<ModelSource, 'flex_frame_mode' | 'flex_frame_start' | 'flex_frame_end'> & Partial<Pick<ModelSource, 'flex_frame_days'>>,
): string {
  return flexFrameText(source)
}

export function describeVersion(version: ModelSource): string {
  const core = coreTimeLabel(version)
  const frame = flexFrameLabel(version)
  const profile = version.profile_name ? `Modell „${version.profile_name}“: ` : ''
  return (
    profile +
    describeTarget(version) +
    breakLabel(version) +
    shiftLabel(version) +
    (core ? `, ${core}` : '') +
    (frame ? `, Gleitzeit-Rahmen ${frame}` : '') +
    (version.late_tolerance_minutes != null ? `, Toleranz ${version.late_tolerance_minutes} Min.` : '')
  )
}

function describeTarget(version: ModelSource): string {
  if (version.on_demand) {
    return `Nach Aufwand ohne Soll${version.monthly_cap_minutes ? `, Monatsgrenze ${formatHours(version.monthly_cap_minutes)} h` : ''}`
  }
  if (version.monthly_minutes != null) {
    return `${formatHours(version.monthly_minutes)} h/Monat an ${version.weekdays.map((d) => WEEKDAYS[d]).join(', ')}`
  }
  const weekly = version.weekly_minutes != null ? `${formatHours(version.weekly_minutes)} h/Woche` : ''
  if (version.flexible) return `${weekly}, flexibel ohne feste Tage`
  if (version.day_minutes && version.uneven) {
    return `${weekly}: ${version.day_minutes
      .map((m, d) => (m > 0 ? `${WEEKDAYS[d]} ${formatHours(m)} h` : null))
      .filter(Boolean)
      .join(', ')}`
  }
  const days = version.weekdays.map((d) => WEEKDAYS[d]).join(', ')
  return `${weekly} an ${days}${version.daily_minutes ? ` (${formatHours(version.daily_minutes)} h/Tag)` : ''}`
}
