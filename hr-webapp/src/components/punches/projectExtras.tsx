import type { TimeEntryWeek } from '../../api/queries/timeEntries'
import type { SpanDraft } from '../../lib/timeEntries'
import { Input } from '../ui/input'
import type { SpanExtras } from './TimeSheetCard'

const NO_PROJECT = ''

/** Projektzeiten im Stundenzettel: Projekt (nur am Tag gültige) und Tätigkeit je Arbeitszeit. */
export function projectExtras(week: TimeEntryWeek): SpanExtras {
  const projects = week.projects ?? []
  const names = week.project_names ?? {}
  const label = (id: number) => names[id] ?? projects.find((p) => p.id === id)?.label ?? `Projekt ${id}`
  return {
    render: (span: SpanDraft, update, workDate) => {
      const extra = span.extra ?? {}
      const value = extra.project_id != null ? String(extra.project_id) : NO_PROJECT
      const options = projects.filter(
        (p) => (!p.valid_from || p.valid_from <= workDate) && (!p.valid_to || workDate <= p.valid_to),
      )
      return (
        <>
          <select
            aria-label="Projekt"
            className="h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm sm:w-56"
            value={value}
            onChange={(e) =>
              update({ extra: { ...extra, project_id: e.target.value === NO_PROJECT ? undefined : Number(e.target.value) } })
            }
          >
            <option value={NO_PROJECT}>{week.project_required ? 'Projekt wählen …' : 'Ohne Projekt'}</option>
            {options.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <Input
            aria-label="Tätigkeit"
            placeholder="Tätigkeit (optional)"
            maxLength={200}
            className="w-full sm:w-56"
            value={typeof extra.note === 'string' ? extra.note : ''}
            onChange={(e) => update({ extra: { ...extra, note: e.target.value || undefined } })}
          />
        </>
      )
    },
    validate: (spans) =>
      week.project_required && spans.some((s) => s.kind === 'WORK' && s.extra?.project_id == null)
        ? 'Bitte jeder Arbeitszeit ein Projekt zuordnen.'
        : null,
    describe: (span) => {
      if (span.kind !== 'WORK' || span.project_id == null) return span.note ?? null
      return span.note ? `${label(span.project_id)} – ${span.note}` : label(span.project_id)
    },
  }
}
