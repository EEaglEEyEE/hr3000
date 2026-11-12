/** Stundenzettel (Zeiten selbst eintragen): Prüfregeln und Anzeige, ohne Komponenten. */
import type { CorrectionRequestCreate } from '../api/queries/correctionRequests'

type Item = CorrectionRequestCreate['items'][number]

/** Eine Zeile im Eingabeformular (Ortszeit "HH:MM"). extra = Zusatzangaben einer Arbeitsspanne, die
 * unverändert mitgeschickt werden (siehe SpanExtras). */
export interface SpanDraft {
  kind: 'WORK' | 'BREAK'
  start: string
  end: string
  end_next_day: boolean
  extra?: Record<string, unknown>
}

function minutes(value: string): number {
  const [hours, mins] = value.split(':').map(Number)
  return hours * 60 + mins
}

function endMinutes(span: SpanDraft): number {
  return minutes(span.end) + (span.end_next_day ? 1440 : 0)
}

/** Dieselben Regeln wie im Backend (schemas/time_entry.py) – für verständliche Meldungen vorab. */
export function validateSpans(spans: SpanDraft[]): string | null {
  if (spans.some((s) => !/^\d{2}:\d{2}$/.test(s.start) || !/^\d{2}:\d{2}$/.test(s.end))) return 'Bitte Beginn und Ende angeben.'
  if (spans.some((s) => endMinutes(s) <= minutes(s.start))) {
    return 'Das Ende muss nach dem Beginn liegen (über Mitternacht: „Folgetag“ ankreuzen).'
  }
  const work = spans.filter((s) => s.kind === 'WORK').sort((a, b) => minutes(a.start) - minutes(b.start))
  const breaks = spans.filter((s) => s.kind === 'BREAK').sort((a, b) => minutes(a.start) - minutes(b.start))
  if (work.length === 0) return 'Bitte mindestens eine Arbeitszeit eintragen.'
  for (let i = 1; i < work.length; i++) {
    if (minutes(work[i].start) < endMinutes(work[i - 1])) return 'Die eingetragenen Zeiten überschneiden sich.'
  }
  for (let i = 1; i < breaks.length; i++) {
    if (minutes(breaks[i].start) < endMinutes(breaks[i - 1])) return 'Die eingetragenen Pausen überschneiden sich.'
  }
  const inside = (pause: SpanDraft) =>
    work.some((w) => minutes(w.start) < minutes(pause.start) && endMinutes(pause) < endMinutes(w))
  if (!breaks.every(inside)) return 'Eine Pause muss innerhalb einer Arbeitszeit liegen.'
  return null
}

/** Selbst eingetragene Zeiten als Spannen „08:00–12:00, Pause 10:00–10:15“ (Kommen/Gehen gepaart). */
export function describeTimeEntry(items: Item[], label: (item: Item) => string | null = () => null): string {
  const parts: { order: number; text: string }[] = []
  const open: Partial<Record<'COME' | 'BREAK_START', { item: Item; order: number }>> = {}
  const clock = (item: Item) => `${item.time}${item.next_day ? ' (Folgetag)' : ''}`
  items.forEach((item, order) => {
    if (item.punch_type === 'COME' || item.punch_type === 'BREAK_START') {
      open[item.punch_type] = { item, order }
    } else if (item.punch_type === 'GO' && open.COME) {
      const extra = label(open.COME.item)
      parts.push({ order: open.COME.order, text: `${clock(open.COME.item)}–${clock(item)}${extra ? ` (${extra})` : ''}` })
      delete open.COME
    } else if (item.punch_type === 'BREAK_END' && open.BREAK_START) {
      parts.push({ order: open.BREAK_START.order, text: `Pause ${clock(open.BREAK_START.item)}–${clock(item)}` })
      delete open.BREAK_START
    }
  })
  // in der Reihenfolge des Beginns (eine Pause endet vor ihrer Arbeitszeit)
  return parts
    .sort((a, b) => a.order - b.order)
    .map((part) => part.text)
    .join(', ')
}

