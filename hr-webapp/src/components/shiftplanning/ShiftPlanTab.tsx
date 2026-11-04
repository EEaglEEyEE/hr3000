import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useDefaultShiftsQuery, useDeleteDefaultShiftMutation } from '../../api/queries/employeeDefaultShifts'
import {
  useDeleteShiftPlanEntryMutation,
  useShiftPlanEntriesQuery,
  useUpsertShiftPlanEntryMutation,
} from '../../api/queries/shiftPlanEntries'
import { useShiftTemplatesQuery } from '../../api/queries/shiftTemplates'
import { ApiError } from '../../api/client'
import { daysFromNowIsoDate, formatDate, todayIsoDate } from '../../lib/format'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { DefaultShiftFormDialog } from './DefaultShiftFormDialog'

const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function maskToLabel(mask: number): string {
  return WEEKDAY_LABELS.filter((_, index) => mask & (1 << index)).join(', ')
}

export function ShiftPlanTab({ employeeId, readOnly = false }: { employeeId: number; readOnly?: boolean }) {
  const defaultShiftsQuery = useDefaultShiftsQuery(employeeId)
  const deleteDefaultShift = useDeleteDefaultShiftMutation(employeeId)
  const [dialogOpen, setDialogOpen] = useState(false)

  const rangeFrom = todayIsoDate()
  const rangeTo = daysFromNowIsoDate(30)
  const entriesQuery = useShiftPlanEntriesQuery(employeeId, rangeFrom, rangeTo)
  const deleteEntry = useDeleteShiftPlanEntryMutation(employeeId)
  const upsertEntry = useUpsertShiftPlanEntryMutation(employeeId)
  const templatesQuery = useShiftTemplatesQuery({ includeWorkTimeModels: true })
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
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-800">Standard-Schicht</h2>
          {!readOnly && (
            <Button size="sm" onClick={() => setDialogOpen(true)}>
              <Plus className="h-4 w-4" />
              Neue Standard-Schicht
            </Button>
          )}
        </div>

        {defaultShiftsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
        {defaultShiftsQuery.isError && (
          <p className="text-red-600">Standard-Schichten konnten nicht geladen werden.</p>
        )}

        {defaultShiftsQuery.data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Von</TableHead>
                <TableHead>Bis</TableHead>
                <TableHead>Vorlage</TableHead>
                <TableHead>Wochentage</TableHead>
                {!readOnly && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {defaultShiftsQuery.data.map((defaultShift) => (
                <TableRow key={defaultShift.id}>
                  <TableCell>{formatDate(defaultShift.valid_from)}</TableCell>
                  <TableCell>
                    {defaultShift.valid_to ? (
                      formatDate(defaultShift.valid_to)
                    ) : (
                      <Badge variant="success">Aktuell</Badge>
                    )}
                  </TableCell>
                  <TableCell>{templateById.get(defaultShift.shift_template_id)?.name ?? '–'}</TableCell>
                  <TableCell>{maskToLabel(defaultShift.weekdays_mask)}</TableCell>
                  {!readOnly && (
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => deleteDefaultShift.mutate(defaultShift.id)}
                      >
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
              {defaultShiftsQuery.data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={readOnly ? 4 : 5} className="text-center text-slate-500">
                    Keine Standard-Schicht hinterlegt.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}

        {!readOnly && (
          <DefaultShiftFormDialog open={dialogOpen} onOpenChange={setDialogOpen} employeeId={employeeId} />
        )}
      </div>

      <div className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-slate-800">
          Ausnahmen (nächste 30 Tage)
        </h2>
        <p className="text-sm text-slate-600">
          Überschreibt für einen einzelnen Tag die Standard-Schicht – z.B. ein zusätzlicher freier
          Tag oder eine abweichende Schicht.
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
                    {templates
                      .filter((template) => !template.is_work_time_model)
                      .map((template) => (
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
