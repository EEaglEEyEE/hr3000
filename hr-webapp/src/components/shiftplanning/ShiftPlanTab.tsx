import { useState, type FormEvent } from 'react'
import { Trash2 } from 'lucide-react'
import {
  useDeleteShiftPlanEntryMutation,
  useShiftPlanEntriesQuery,
  useUpsertShiftPlanEntryMutation,
} from '../../api/queries/shiftPlanEntries'
import { useShiftTemplatesQuery } from '../../api/queries/shiftTemplates'
import { useWorkTimeModelQuery } from '../../api/queries/workTimeModel'
import { ApiError } from '../../api/client'
import { daysFromNowIsoDate, formatDate, todayIsoDate } from '../../lib/format'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { WorkTimeModelSummary } from '../workTimeModel/WorkTimeModelTab'

/** Schichtplan eines Mitarbeiters: regelmäßige Arbeitszeit (aus dem Arbeitszeitmodell, nur lesend)
 *  und Ausnahmen für einzelne Tage. */
export function ShiftPlanTab({ employeeId, readOnly = false }: { employeeId: number; readOnly?: boolean }) {
  const modelQuery = useWorkTimeModelQuery(employeeId)
  const rangeFrom = todayIsoDate()
  const rangeTo = daysFromNowIsoDate(30)
  const entriesQuery = useShiftPlanEntriesQuery(employeeId, rangeFrom, rangeTo)
  const deleteEntry = useDeleteShiftPlanEntryMutation(employeeId)
  const upsertEntry = useUpsertShiftPlanEntryMutation(employeeId)
  const templatesQuery = useShiftTemplatesQuery({ enabled: !readOnly })
  const templates = templatesQuery.data ?? []

  const [exceptionDate, setExceptionDate] = useState(rangeFrom)
  const [exceptionIsWorkday, setExceptionIsWorkday] = useState(false)
  const [exceptionTemplateId, setExceptionTemplateId] = useState('')
  const [exceptionError, setExceptionError] = useState<string | null>(null)

  const templateById = new Map(templates.map((template) => [template.id, template]))

  async function handleAddException(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setExceptionError(null)
    try {
      await upsertEntry.mutateAsync({
        date: exceptionDate,
        payload: {
          is_workday: exceptionIsWorkday,
          shift_template_id: exceptionIsWorkday && exceptionTemplateId ? Number(exceptionTemplateId) : undefined,
        },
      })
      setExceptionTemplateId('')
    } catch (err) {
      if (err instanceof ApiError && err.code === 'TARGET_MINUTES_REQUIRED') {
        setExceptionError('Für einen Arbeitstag muss eine Schichtvorlage gewählt werden.')
      } else if (err instanceof ApiError && err.code === 'REST_PERIOD_VIOLATION') {
        setExceptionError('Die gesetzliche Mindestruhezeit von 11 Stunden (§5 ArbZG) wird unterschritten.')
      } else {
        setExceptionError('Speichern fehlgeschlagen.')
      }
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex max-w-3xl flex-col gap-2">
        <h2 className="text-sm font-semibold text-slate-800">Regelmäßige Arbeitszeit</h2>
        <WorkTimeModelSummary model={modelQuery.data} loading={modelQuery.isLoading} />
        {!readOnly && (
          <p className="text-sm text-slate-600">
            Arbeitstage, Soll und feste Uhrzeiten (Schichtvorlage) stehen im Arbeitszeitmodell – ändern im Reiter
            „Arbeitszeitmodell“.
          </p>
        )}
      </div>

      <div className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-slate-800">
          Ausnahmen (nächste 30 Tage)
        </h2>
        <p className="text-sm text-slate-600">
          Überschreibt für einen einzelnen Tag die regelmäßige Arbeitszeit – z.B. ein zusätzlicher freier
          Tag oder eine abweichende Schicht. Ohne Tagessoll (flexibel, nach Aufwand) liefert eine Schicht nur
          die Uhrzeiten.
        </p>

        {entriesQuery.data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Datum</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Vorlage</TableHead>
                {!readOnly && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {entriesQuery.data.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>{formatDate(entry.date)}</TableCell>
                  <TableCell>
                    {entry.is_workday ? (
                      <Badge variant="info">Arbeitstag</Badge>
                    ) : (
                      <Badge>Frei</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {entry.shift_template_id ? templateById.get(entry.shift_template_id)?.name ?? '–' : '–'}
                  </TableCell>
                  {!readOnly && (
                    <TableCell>
                      <Button variant="ghost" size="icon" onClick={() => deleteEntry.mutate(entry.date)}>
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
              {entriesQuery.data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={readOnly ? 3 : 4} className="text-center text-slate-500">
                    Keine Ausnahmen im Zeitraum.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}

        {!readOnly && (
          <form
            className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-4"
            onSubmit={handleAddException}
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="exception_date">Datum</Label>
              <Input
                id="exception_date"
                type="date"
                min={rangeFrom}
                max={rangeTo}
                value={exceptionDate}
                onChange={(event) => setExceptionDate(event.target.value)}
              />
            </div>
            <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300"
                checked={exceptionIsWorkday}
                onChange={(event) => setExceptionIsWorkday(event.target.checked)}
              />
              Arbeitstag
            </label>
            {exceptionIsWorkday && (
              <div className="flex flex-col gap-1.5">
                <Label>Vorlage</Label>
                <Select value={exceptionTemplateId} onValueChange={setExceptionTemplateId}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Vorlage wählen" />
                  </SelectTrigger>
                  <SelectContent>
                    {templates.map((template) => (
                      <SelectItem key={template.id} value={String(template.id)}>
                        {template.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <Button type="submit" disabled={upsertEntry.isPending}>
              Ausnahme speichern
            </Button>
          </form>
        )}
        {exceptionError && <p className="text-sm text-red-600">{exceptionError}</p>}
      </div>
    </div>
  )
}
