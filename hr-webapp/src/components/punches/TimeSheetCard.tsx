import { useState, type FormEvent, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  useCreateTimeEntryMutation,
  useDeleteTimeEntryMutation,
  useOwnTimeEntriesQuery,
  useWithdrawTimeEntryMutation,
  type TimeEntryDay,
  type TimeEntryWeek,
  type TimeSpanIn,
  type TimeSpanOut,
} from '../../api/queries/timeEntries'
import { addDaysIsoDate, formatDate, formatHoursMinutes, mondayOfWeek, todayIsoDate, weekdayShortLabel } from '../../lib/format'
import { PUNCH_SOURCE_LABELS } from '../../lib/labels'
import { validateSpans, type SpanDraft } from '../../lib/timeEntries'
import { projectExtras } from './projectExtras'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

/** Zusatzfelder je Arbeitsspanne – von außen eingesetzt, damit der Stundenzettel selbst schlank bleibt. */
export interface SpanExtras {
  render: (span: SpanDraft, update: (patch: Partial<SpanDraft>) => void, workDate: string) => ReactNode
  /** Fehlermeldung, wenn etwas fehlt (z. B. Projekt Pflicht), sonst null. */
  validate?: (spans: SpanDraft[]) => string | null
  /** Anzeige zu einer wirksamen bzw. beantragten Spanne (z. B. Projektname). */
  describe?: (span: TimeSpanOut) => string | null
}

function clock(iso: string, timeZone: string): string {
  const value = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`
  return new Date(value).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone })
}

function spanLabel(span: TimeSpanOut, timeZone: string): string {
  const range = `${clock(span.start, timeZone)}–${span.end ? clock(span.end, timeZone) : '…'}`
  return span.kind === 'BREAK' ? `Pause ${range}` : range
}

const NEW_WORK: SpanDraft = { kind: 'WORK', start: '08:00', end: '12:00', end_next_day: false }

function hhmm(total: number): string {
  return `${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

/** Neue Pause: 30 Minuten in der Mitte der ersten Arbeitszeit (liegt so gleich innerhalb). */
function defaultBreak(spans: SpanDraft[]): SpanDraft {
  const work = spans.find((s) => s.kind === 'WORK' && /^\d{2}:\d{2}$/.test(s.start) && /^\d{2}:\d{2}$/.test(s.end))
  if (!work) return { kind: 'BREAK', start: '12:00', end: '12:30', end_next_day: false }
  const [sh, sm] = work.start.split(':').map(Number)
  const [eh, em] = work.end.split(':').map(Number)
  const start = sh * 60 + sm
  const end = eh * 60 + em + (work.end_next_day ? 1440 : 0)
  const middle = start + Math.max(Math.floor((end - start - 30) / 2), 1)
  return { kind: 'BREAK', start: hhmm(middle), end: hhmm(Math.min(middle + 30, end - 1)), end_next_day: false }
}

/** „Mein Bereich“ → Zeiterfassung: Stundenzettel (Einstellung „Zeiten selbst eintragen“). Wochenraster
 * Mo–So; je Tag die wirksamen Zeiten (mit Quelle), offene Anträge und ein Formular für neue Spannen. */
export function TimeSheetCard({ extras }: { extras?: SpanExtras }) {
  const [monday, setMonday] = useState(() => mondayOfWeek(todayIsoDate()))
  const sunday = addDaysIsoDate(monday, 6)
  const query = useOwnTimeEntriesQuery(monday, sunday)
  const [openDay, setOpenDay] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const week = query.data
  const effectiveExtras = extras ?? (week?.projects_enabled ? projectExtras(week) : undefined)

  if (query.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (query.isError || !week) return <p className="text-red-600">Stundenzettel konnte nicht geladen werden.</p>
  if (!week.enabled) return null

  const total = week.days.reduce((sum, day) => sum + (day.actual_minutes ?? 0), 0)
  const nextDisabled = addDaysIsoDate(monday, 7) > week.today

  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div>
        <p className="text-sm font-medium text-slate-800">Stundenzettel</p>
        <p className="text-sm text-slate-500">
          Arbeitszeiten selbst eintragen – {week.backdate_days === 0 ? 'nur für heute' : `bis zu ${week.backdate_days} Tage rückwirkend`}.{' '}
          {week.approval_required
            ? 'Die Zeiten zählen erst, wenn sie genehmigt sind.'
            : 'Die Zeiten zählen sofort und sind als „selbst eingetragen“ gekennzeichnet.'}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" aria-label="Vorige Woche" onClick={() => setMonday(addDaysIsoDate(monday, -7))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="px-2 text-sm font-medium text-slate-700">
            {formatDate(monday)} – {formatDate(sunday)}
          </span>
          <Button
            variant="outline"
            size="icon"
            aria-label="Nächste Woche"
            disabled={nextDisabled}
            onClick={() => setMonday(addDaysIsoDate(monday, 7))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <span className="text-sm text-slate-600">Woche: {formatHoursMinutes(total)} Std.</span>
      </div>
      {message && <p className="text-sm text-emerald-700">{message}</p>}
      <ul className="flex flex-col divide-y divide-slate-100">
        {week.days.map((day) => (
          <DayRow
            key={day.work_date}
            day={day}
            week={week}
            extras={effectiveExtras}
            open={openDay === day.work_date}
            onOpen={() => {
              setOpenDay(day.work_date)
              setMessage(null)
            }}
            onClose={(text) => {
              setOpenDay(null)
              if (text) setMessage(text)
            }}
          />
        ))}
      </ul>
    </div>
  )
}

function DayRow({
  day,
  week,
  extras,
  open,
  onOpen,
  onClose,
}: {
  day: TimeEntryDay
  week: TimeEntryWeek
  extras?: SpanExtras
  open: boolean
  onOpen: () => void
  onClose: (message?: string) => void
}) {
  const remove = useDeleteTimeEntryMutation()
  const withdraw = useWithdrawTimeEntryMutation()
  const [error, setError] = useState<string | null>(null)
  const isToday = day.work_date === week.today
  const onError = (err: unknown) => setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.')
  const spans = day.spans ?? []
  const pending = day.pending ?? []

  return (
    <li className="flex flex-col gap-2 py-2">
      {/* Handy: Datum und Knopf oben, Zeiten darunter; ab sm eine Zeile */}
      <div className="grid grid-cols-[1fr_auto] items-start gap-x-3 gap-y-1 sm:grid-cols-[6rem_1fr_auto]">
        <div className={`col-start-1 row-start-1 pt-1 text-sm ${isToday ? 'font-semibold text-sky-800' : 'text-slate-700'}`}>
          {weekdayShortLabel(day.work_date)} {day.work_date.slice(8, 10)}.{day.work_date.slice(5, 7)}.
        </div>
        <div className="col-span-2 row-start-2 flex min-w-0 flex-wrap items-center gap-1.5 sm:col-span-1 sm:col-start-2 sm:row-start-1 sm:pt-1">
          {spans.length === 0 && pending.length === 0 && <span className="text-sm text-slate-400">–</span>}
          {spans.map((span, index) => {
            const detail = extras?.describe?.(span)
            return (
              <span
                key={`s-${span.punch_id ?? index}`}
                className={`inline-flex max-w-full flex-wrap items-center gap-x-1 rounded border px-1.5 py-0.5 text-xs ${
                  span.kind === 'BREAK' ? 'border-slate-200 bg-slate-50 text-slate-500' : 'border-slate-200 bg-white text-slate-800'
                }`}
              >
                <span className="whitespace-nowrap">{spanLabel(span, week.timezone)}</span>
                {detail && <span className="min-w-0 break-words text-slate-500">· {detail}</span>}
                {span.source && span.source !== 'SELF_ENTRY' && span.kind === 'WORK' && (
                  <span className="text-slate-400">({PUNCH_SOURCE_LABELS[span.source]})</span>
                )}
                {span.deletable && span.punch_id != null && (
                  <button
                    type="button"
                    aria-label={`${spanLabel(span, week.timezone)} löschen`}
                    className="text-red-600 hover:text-red-800"
                    disabled={remove.isPending}
                    onClick={() => {
                      setError(null)
                      if (window.confirm(`${spanLabel(span, week.timezone)} am ${formatDate(day.work_date)} löschen?`)) {
                        remove.mutate(span.punch_id!, { onError })
                      }
                    }}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </span>
            )
          })}
          {pending.map((entry) => (
            <span key={`p-${entry.request_id}`} className="inline-flex flex-wrap items-center gap-1">
              {entry.spans.map((span, index) => {
                const detail = extras?.describe?.(span)
                return (
                  <Badge key={index} variant="warning">
                    {spanLabel(span, week.timezone)}
                    {detail ? ` · ${detail}` : ''}
                  </Badge>
                )
              })}
              <span className="text-xs text-amber-700">beantragt</span>
              <button
                type="button"
                className="text-xs text-sky-700 underline"
                disabled={withdraw.isPending}
                onClick={() => {
                  setError(null)
                  withdraw.mutate(entry.request_id, { onError })
                }}
              >
                Zurückziehen
              </button>
            </span>
          ))}
        </div>
        <div className="col-start-2 row-start-1 flex items-center justify-end gap-2 sm:col-start-3">
          {day.actual_minutes != null && (
            <span className="text-sm text-slate-600">{formatHoursMinutes(day.actual_minutes)} Std.</span>
          )}
          {day.can_enter && !open && (
            <Button size="sm" variant="outline" onClick={onOpen}>
              <Plus className="h-4 w-4" />
              Eintragen
            </Button>
          )}
        </div>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {open && <DayForm day={day} week={week} extras={extras} onClose={onClose} />}
    </li>
  )
}

function DayForm({
  day,
  week,
  extras,
  onClose,
}: {
  day: TimeEntryDay
  week: TimeEntryWeek
  extras?: SpanExtras
  onClose: (message?: string) => void
}) {
  const create = useCreateTimeEntryMutation()
  const [spans, setSpans] = useState<SpanDraft[]>([{ ...NEW_WORK }])
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)

  function update(index: number, patch: Partial<SpanDraft>) {
    setSpans((current) => current.map((span, i) => (i === index ? { ...span, ...patch } : span)))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const problem = validateSpans(spans) ?? extras?.validate?.(spans) ?? null
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    try {
      const payload = spans.map(
        (span): TimeSpanIn => ({
          ...(span.kind === 'WORK' ? span.extra : undefined),
          kind: span.kind,
          start: span.start,
          end: span.end,
          end_next_day: span.end_next_day,
        }),
      )
      const result = await create.mutateAsync({ work_date: day.work_date, spans: payload, comment: comment.trim() || null })
      onClose(
        result.status === 'PENDING'
          ? `Zeiten für den ${formatDate(day.work_date)} zur Genehmigung gesendet.`
          : `Zeiten für den ${formatDate(day.work_date)} eingetragen.`,
      )
    } catch (err) {
      setError(err instanceof ApiError && err.code ? err.message : 'Bitte Eingaben prüfen.')
    }
  }

  return (
    <form className="flex flex-col gap-3 rounded-md bg-slate-50 p-3" onSubmit={handleSubmit}>
      <p className="text-sm font-medium text-slate-700">Zeiten am {formatDate(day.work_date)}</p>
      <div className="flex flex-col gap-2">
        {spans.map((span, index) => (
          <div key={index} className="flex flex-wrap items-center gap-2">
            <span className="w-full text-xs font-medium text-slate-600 sm:w-14">{span.kind === 'WORK' ? 'Arbeit' : 'Pause'}</span>
            <Input
              type="time"
              aria-label="Beginn"
              className="w-28"
              required
              value={span.start}
              onChange={(e) => update(index, { start: e.target.value })}
            />
            <span className="text-slate-500">–</span>
            <Input
              type="time"
              aria-label="Ende"
              className="w-28"
              required
              value={span.end}
              onChange={(e) => update(index, { end: e.target.value })}
            />
            {span.kind === 'WORK' && (
              <label className="flex items-center gap-1.5 text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={span.end_next_day}
                  onChange={(e) => update(index, { end_next_day: e.target.checked })}
                />
                Folgetag
              </label>
            )}
            {span.kind === 'WORK' && extras?.render(span, (patch) => update(index, patch), day.work_date)}
            {spans.length > 1 && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Zeile entfernen"
                onClick={() => setSpans((current) => current.filter((_, i) => i !== index))}
              >
                <Trash2 className="h-4 w-4 text-red-600" />
              </Button>
            )}
          </div>
        ))}
        {spans.length < 10 && (
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className="text-xs text-sky-700 underline"
              onClick={() => {
                const last = [...spans].reverse().find((s) => s.kind === 'WORK')
                const start = last && !last.end_next_day ? last.end : '13:00'
                setSpans((current) => [...current, { ...NEW_WORK, start, end: start < '17:00' ? '17:00' : '23:59' }])
              }}
            >
              weitere Arbeitszeit
            </button>
            <button
              type="button"
              className="text-xs text-sky-700 underline"
              onClick={() => setSpans((current) => [...current, defaultBreak(current)])}
            >
              Pause hinzufügen
            </button>
          </div>
        )}
      </div>
      {week.approval_required && (
        <label className="flex flex-col gap-1 text-sm">
          Hinweis für die Genehmigung (optional)
          <Input maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => onClose()}>
          Abbrechen
        </Button>
        <Button type="submit" size="sm" disabled={create.isPending}>
          {week.approval_required ? 'Zur Genehmigung senden' : 'Speichern'}
        </Button>
      </div>
    </form>
  )
}
