import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { templateBreakLabel, useShiftTemplatesQuery } from '../../api/queries/shiftTemplates'
import {
  useDeleteWorkTimeModelVersionMutation,
  useFeaturesQuery,
  useSetWorkTimeModelMutation,
  useUpdateWorkTimeModelVersionMutation,
  useWorkTimeModelHistoryQuery,
  useWorkTimeModelQuery,
  type WorkTimeModel,
  type WorkTimeModelVersion,
} from '../../api/queries/workTimeModel'
import { formatDate } from '../../lib/format'
import { cn } from '../../lib/utils'
import {
  CoreTimeFields,
  coreTimeFromApi,
  coreTimeLabel,
  coreTimePayload,
  coreTimeValid,
  DEFAULT_CORE_TIME,
  type CoreTimeValue,
} from '../coreTime/CoreTimeFields'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const WORKWEEK = [0, 1, 2, 3, 4]

function toIsoDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function hhmm(value: string | null | undefined): string {
  return value ? value.slice(0, 5) : ''
}

/** Pause einer Fassung als Text, z. B. ", Pause 30 Min." (leer = Pausenregeln). */
function breakLabel(source: {
  break_minutes?: number | null
  break_after_minutes?: number
  break_start?: string | null
  break_end?: string | null
}): string {
  if (source.break_minutes) {
    const after = source.break_after_minutes ? ` ab ${formatHours(source.break_after_minutes)} Std.` : ''
    return `, Pause ${source.break_minutes} Min.${after}`
  }
  if (source.break_start && source.break_end) return `, Pause ${hhmm(source.break_start)}–${hhmm(source.break_end)}`
  return ''
}

/** Schichtvorlage einer Fassung als Text, z. B. ", Schicht „Früh“ 06:00–14:30". */
function shiftLabel(source: { shift_template_name?: string | null; shift_start?: string | null; shift_end?: string | null }): string {
  if (!source.shift_template_name) return ''
  const times = source.shift_start && source.shift_end ? ` ${hhmm(source.shift_start)}–${hhmm(source.shift_end)}` : ''
  return `, Schicht „${source.shift_template_name}“${times}`
}

function formatHours(minutes: number): string {
  return (minutes / 60).toLocaleString('de-DE', { maximumFractionDigits: 2 })
}

function decimal(value: number): string {
  return String(value).replace('.', ',')
}

/** Wie viele der gewählten Wochentage hat der Kalendermonat von `day`? */
function workdaysInMonth(day: Date, weekdays: number[]): number {
  const year = day.getFullYear()
  const month = day.getMonth()
  const length = new Date(year, month + 1, 0).getDate()
  let count = 0
  for (let d = 1; d <= length; d++) {
    if (weekdays.includes((new Date(year, month, d).getDay() + 6) % 7)) count++
  }
  return count
}

// Arbeitstage: feste Tage, flexibel (Wochensoll ohne feste Tage) oder nach Aufwand (ohne Soll).
type DaysKind = 'fixed' | 'flex' | 'onDemand'
// Soll bei festen Tagen: Wochenstunden (gleichmäßig oder je Wochentag) oder festes Monatssoll.
type Period = 'week' | 'month'

export function WorkTimeModelTab({ employeeId, canEdit }: { employeeId: number; canEdit: boolean }) {
  const modelQuery = useWorkTimeModelQuery(employeeId)
  const setModel = useSetWorkTimeModelMutation(employeeId)
  const updateVersion = useUpdateWorkTimeModelVersionMutation(employeeId)
  const deleteVersion = useDeleteWorkTimeModelVersionMutation(employeeId)
  const historyQuery = useWorkTimeModelHistoryQuery(employeeId)
  const templatesQuery = useShiftTemplatesQuery({ enabled: canEdit })
  // Schichtvorlagen gibt es mit Schichtplanung (Einstellungen); eine schon zugeordnete bleibt sichtbar.
  const shiftPlanningEnabled = useFeaturesQuery().data?.shift_planning_enabled ?? false
  const templates = templatesQuery.data ?? []
  const model = modelQuery.data
  // Nachträgliche Änderung einer bestehenden Fassung statt neuer Fassung ab Stichtag
  const [editing, setEditing] = useState<WorkTimeModelVersion | null>(null)
  const formRef = useRef<HTMLFormElement>(null)

  const [daysKind, setDaysKind] = useState<DaysKind>('fixed')
  const [period, setPeriod] = useState<Period>('week')
  const [perDay, setPerDay] = useState(false)
  const [weeklyHours, setWeeklyHours] = useState('40')
  const [weekdays, setWeekdays] = useState<number[]>(WORKWEEK)
  const [monthlyHours, setMonthlyHours] = useState('')
  const [capHours, setCapHours] = useState('')
  const [dailyHours, setDailyHours] = useState<string[]>(['8', '8', '8', '8', '8', '', ''])
  // Pause: "rules" = keine eigene (Pause der Schichtvorlage bzw. Pausenregeln), "minutes", "window".
  const [breakKind, setBreakKind] = useState<'rules' | 'minutes' | 'window'>('rules')
  const [breakMinutes, setBreakMinutes] = useState('30')
  const [breakAfterHours, setBreakAfterHours] = useState('')
  const [breakStart, setBreakStart] = useState('12:00')
  const [breakEnd, setBreakEnd] = useState('12:30')
  // Schichtvorlage nur für die Uhrzeiten ('' = keine festen Uhrzeiten)
  const [shiftTemplateId, setShiftTemplateId] = useState('')
  // Vorlage der geladenen Fassung (auch eine alte, archivierte Fassung einer Vorlage)
  const [loadedShift, setLoadedShift] = useState<{ id: number; name: string; breakFromTemplate: boolean } | null>(null)
  const [coreTime, setCoreTime] = useState<CoreTimeValue>(DEFAULT_CORE_TIME)
  const [validFrom, setValidFrom] = useState(() => toIsoDate(new Date()))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const mode =
    daysKind === 'onDemand' ? 'onDemand' : daysKind === 'flex' ? 'flex' : period === 'month' ? 'monthly' : perDay ? 'perDay' : 'even'
  const parsedDaily = dailyHours.map((value) => (value.trim() ? Number(value.replace(',', '.')) : 0))
  const dailyValid = parsedDaily.every((h) => Number.isFinite(h) && h >= 0 && h <= 10) && parsedDaily.some((h) => h > 0)
  const dailySum = parsedDaily.reduce((sum, h) => sum + (Number.isFinite(h) ? h : 0), 0)
  const hours = Number(weeklyHours.replace(',', '.'))
  const cap = capHours.trim() ? Number(capHours.replace(',', '.')) : null
  const capValid = cap === null || (Number.isFinite(cap) && cap > 0 && cap <= 400)
  const monthly = Number(monthlyHours.replace(',', '.'))
  const hoursValid =
    mode === 'onDemand'
      ? capValid
      : mode === 'perDay'
        ? dailyValid
        : mode === 'monthly'
          ? monthlyHours.trim() !== '' && Number.isFinite(monthly) && monthly > 0 && monthly <= 260
          : Number.isFinite(hours) && hours > 0 && hours <= 60
  const breakMinutesNumber = Number(breakMinutes)
  const breakAfter = breakAfterHours.trim() ? Number(breakAfterHours.replace(',', '.')) : null
  const breakValid =
    breakKind === 'rules' ||
    (breakKind === 'minutes'
      ? Number.isInteger(breakMinutesNumber) &&
        breakMinutesNumber > 0 &&
        breakMinutesNumber <= 240 &&
        (breakAfter === null || (Number.isFinite(breakAfter) && breakAfter >= 0 && breakAfter <= 16))
      : breakStart !== '' && breakEnd !== '' && breakStart < breakEnd)
  const breakPayload =
    breakKind === 'minutes'
      ? { break_minutes: breakMinutesNumber, ...(breakAfter ? { break_after_hours: breakAfter } : {}) }
      : breakKind === 'window'
        ? { break_start: breakStart, break_end: breakEnd }
        : {}
  const dailyPreview = hoursValid && weekdays.length > 0 ? formatHours(Math.round((hours * 60) / weekdays.length)) : null
  // Monatssoll: Tagessoll je nach Monat zwischen (Monat mit den meisten) und (Monat mit den wenigsten Arbeitstagen).
  const monthlyPreview =
    mode === 'monthly' && hoursValid && weekdays.length > 0
      ? {
          low: formatHours(Math.round((monthly * 60) / (4 * weekdays.length + Math.min(weekdays.length, 3)))),
          high: formatHours(Math.round((monthly * 60) / (4 * weekdays.length))),
        }
      : null

  const selectedTemplate = templates.find((template) => String(template.id) === shiftTemplateId)
  const templateBreak = selectedTemplate
    ? templateBreakLabel(selectedTemplate)
    : loadedShift && String(loadedShift.id) === shiftTemplateId && loadedShift.breakFromTemplate
      ? 'laut Vorlage'
      : ''
  const templateOptions =
    loadedShift && !templates.some((template) => template.id === loadedShift.id)
      ? [...templates.map((t) => ({ id: t.id, label: templateOptionLabel(t) })), { id: loadedShift.id, label: loadedShift.name }]
      : templates.map((t) => ({ id: t.id, label: templateOptionLabel(t) }))

  function toggleWeekday(day: number) {
    setWeekdays((current) =>
      current.includes(day) ? current.filter((value) => value !== day) : [...current, day].sort(),
    )
  }

  function togglePerDay(checked: boolean) {
    if (checked) {
      // Vorschlag: bisherige Wochenstunden gleichmäßig auf die gewählten Tage
      const each = hoursValid && weekdays.length > 0 ? Math.round((hours * 60) / weekdays.length) / 60 : 8
      setDailyHours(WEEKDAYS.map((_, day) => (weekdays.includes(day) ? decimal(Math.round(each * 100) / 100) : '')))
    } else if (dailyValid) {
      setWeeklyHours(decimal(Math.round(dailySum * 100) / 100))
      setWeekdays(parsedDaily.flatMap((h, day) => (h > 0 ? [day] : [])))
    }
    setPerDay(checked)
  }

  // Formular immer mit dem aktuell gültigen Modell vorbelegen (einmal je geladenem Stand).
  const loadedFor = useRef<string | null>(null)
  useEffect(() => {
    const key = model ? JSON.stringify(model) : null
    if (!model?.configured || key === loadedFor.current) return
    loadedFor.current = key
    loadCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model])

  function loadCurrent() {
    if (!model?.configured) return
    loadFrom(model)
  }

  function loadFrom(source: WorkTimeModel | WorkTimeModelVersion) {
    if (source.break_minutes && !source.break_from_template) {
      setBreakKind('minutes')
      setBreakMinutes(String(source.break_minutes))
      setBreakAfterHours(source.break_after_minutes ? decimal(source.break_after_minutes / 60) : '')
    } else if (source.break_start && source.break_end && !source.break_from_template) {
      setBreakKind('window')
      setBreakStart(hhmm(source.break_start))
      setBreakEnd(hhmm(source.break_end))
    } else {
      setBreakKind('rules')
    }
    setShiftTemplateId(source.shift_template_id ? String(source.shift_template_id) : '')
    setLoadedShift(
      source.shift_template_id
        ? { id: source.shift_template_id, name: source.shift_template_name ?? 'Schichtvorlage', breakFromTemplate: !!source.break_from_template }
        : null,
    )
    setCoreTime(coreTimeFromApi(source))
    if (source.on_demand) {
      setDaysKind('onDemand')
      setCapHours(source.monthly_cap_minutes ? decimal(source.monthly_cap_minutes / 60) : '')
      return
    }
    if (source.monthly_minutes != null) {
      setDaysKind('fixed')
      setPeriod('month')
      setMonthlyHours(decimal(source.monthly_minutes / 60))
      if (source.weekdays.length > 0) setWeekdays(source.weekdays)
      return
    }
    if (source.weekly_minutes === null || source.weekly_minutes === undefined) return
    setWeeklyHours(decimal(source.weekly_minutes / 60))
    if (source.weekdays.length > 0) setWeekdays(source.weekdays)
    if (source.day_minutes) {
      setDailyHours(source.day_minutes.map((m) => (m > 0 ? decimal(m / 60) : '')))
    }
    setDaysKind(source.flexible ? 'flex' : 'fixed')
    setPeriod('week')
    setPerDay(!!source.uneven)
  }

  function startEditing(version: WorkTimeModelVersion) {
    setEditing(version)
    setError(null)
    setSaved(false)
    loadFrom(version)
    setValidFrom(version.valid_from)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function stopEditing() {
    setEditing(null)
    setValidFrom(toIsoDate(new Date()))
    loadCurrent()
  }

  async function handleDelete(version: WorkTimeModelVersion) {
    if (!window.confirm(`Fassung ab ${formatDate(version.valid_from)} löschen? Die vorherige Fassung gilt dann weiter.`)) return
    setError(null)
    try {
      await deleteVersion.mutateAsync(version.id)
      if (editing?.id === version.id) stopEditing()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Löschen fehlgeschlagen.')
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSaved(false)
    const modelPayload =
      mode === 'onDemand'
        ? { on_demand: true, flexible: false, monthly_cap_hours: cap, valid_from: validFrom }
        : mode === 'perDay'
        ? { daily_hours: parsedDaily, flexible: false, on_demand: false, valid_from: validFrom }
        : mode === 'monthly'
        ? { monthly_hours: monthly, weekdays, flexible: false, on_demand: false, valid_from: validFrom }
        : mode === 'flex'
          ? { weekly_hours: hours, flexible: true, on_demand: false, valid_from: validFrom }
          : { weekly_hours: hours, weekdays, flexible: false, on_demand: false, valid_from: validFrom }
    const payload = {
      ...modelPayload,
      ...breakPayload,
      shift_template_id: shiftTemplateId ? Number(shiftTemplateId) : null,
      ...coreTimePayload(coreTime),
    }
    try {
      if (editing) {
        await updateVersion.mutateAsync({ versionId: editing.id, payload })
        setEditing(null)
      } else {
        await setModel.mutateAsync(payload)
      }
      setSaved(true)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status !== 422
          ? err.message
          : 'Bitte Stunden (max. 10 je Tag, 60 je Woche bzw. 260 je Monat), mindestens einen Arbeitstag und ein Datum angeben.',
      )
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <WorkTimeModelSummary model={model} loading={modelQuery.isLoading} />

      {canEdit ? (
        <form
          ref={formRef}
          className={cn(
            'flex flex-col gap-4 rounded-md border bg-white p-4',
            editing ? 'border-amber-300 ring-1 ring-amber-200' : 'border-slate-200',
          )}
          onSubmit={handleSubmit}
        >
          <p className="font-medium text-slate-900">
            {editing
              ? `Fassung ${formatRange(editing)} nachträglich ändern`
              : 'Neues Arbeitszeitmodell ab Stichtag'}
          </p>

          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">Modell</legend>
            <div className="flex flex-wrap gap-2 text-sm">
              {(
                [
                  ['fixed', 'Feste Arbeitstage'],
                  ['flex', 'Flexibel ohne feste Tage'],
                  ['onDemand', 'Nach Aufwand (Aushilfe)'],
                ] as const
              ).map(([kind, label]) => (
                <Button
                  key={kind}
                  type="button"
                  size="sm"
                  variant={daysKind === kind ? 'default' : 'outline'}
                  aria-pressed={daysKind === kind}
                  onClick={() => setDaysKind(kind)}
                >
                  {label}
                </Button>
              ))}
            </div>
          </fieldset>

          {daysKind === 'fixed' && (
            <fieldset className="flex flex-col gap-1.5">
              <legend className="mb-1.5 text-sm font-medium">Soll</legend>
              <div className="flex flex-wrap gap-2 text-sm">
                <Button
                  type="button"
                  size="sm"
                  variant={period === 'week' ? 'default' : 'outline'}
                  aria-pressed={period === 'week'}
                  onClick={() => setPeriod('week')}
                >
                  Wochenstunden
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={period === 'month' ? 'default' : 'outline'}
                  aria-pressed={period === 'month'}
                  onClick={() => setPeriod('month')}
                >
                  Monatsstunden (fest)
                </Button>
              </div>
            </fieldset>
          )}

          {mode === 'onDemand' && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cap-hours">Monatsgrenze in Stunden (optional, z. B. für Minijob)</Label>
              <Input
                id="cap-hours"
                inputMode="decimal"
                className="w-32"
                placeholder="keine"
                value={capHours}
                onChange={(e) => setCapHours(e.target.value)}
              />
              <p className="text-sm text-slate-500">
                Kein Soll und kein Gleitzeitkonto: jede Stempelung zählt als Ist-Zeit, Monate ohne Einsatz sind kein Minus,
                und es gibt keine „fehlt“- oder „außerplanmäßig“-Tage. Geplante Schichten liefern nur die Uhrzeiten.
                Abgerechnet werden die Ist-Stunden je Monat (Monatsbericht, Lohn-Export). Mit Monatsgrenze erscheint ab 90 %
                ein Hinweis unter „Zu klären“. Urlaub und Feiertagsbezahlung laufen über die Lohnabrechnung.
              </p>
            </div>
          )}

          {mode === 'flex' && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="flex-hours">Wochenstunden (ungefähr)</Label>
              <Input id="flex-hours" inputMode="decimal" className="w-32" value={weeklyHours} onChange={(e) => setWeeklyHours(e.target.value)} />
              <p className="text-sm text-slate-500">
                Kein Tagessoll und keine festen Arbeitstage: abgerechnet wird je Woche (Soll = Wochenstunden). An keinem Tag gilt
                eine Stempelung als „außerplanmäßig“ oder ein Tag als „fehlt“. Urlaub/Feiertage an Mo–Fr werden mit Wochenstunden ÷ 5
                gutgeschrieben.
              </p>
            </div>
          )}

          {mode === 'monthly' && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="monthly-hours">Monatsstunden</Label>
              <Input
                id="monthly-hours"
                inputMode="decimal"
                className="w-32"
                placeholder="z. B. 108,5"
                value={monthlyHours}
                onChange={(event) => setMonthlyHours(event.target.value)}
              />
            </div>
          )}

          {daysKind === 'fixed' && period === 'week' && (
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={perDay} onChange={(event) => togglePerDay(event.target.checked)} />
              Stunden je Wochentag unterschiedlich (Teilzeit)
            </label>
          )}

          {mode === 'perDay' && (
            <div className="flex flex-col gap-1.5">
              <Label>Stunden je Wochentag (leer = frei)</Label>
              <div className="grid grid-cols-7 gap-1.5">
                {WEEKDAYS.map((label, day) => (
                  <div key={label} className="flex flex-col items-center gap-1">
                    <span className="text-xs text-slate-500">{label}</span>
                    <Input
                      inputMode="decimal"
                      aria-label={`Stunden ${label}`}
                      className="w-full px-1 text-center"
                      value={dailyHours[day]}
                      onChange={(event) =>
                        setDailyHours((current) => current.map((value, index) => (index === day ? event.target.value : value)))
                      }
                    />
                  </div>
                ))}
              </div>
              <p className="text-sm text-slate-500">
                = {dailySum.toLocaleString('de-DE', { maximumFractionDigits: 2 })} h pro Woche an{' '}
                {parsedDaily.filter((h) => h > 0).length} Arbeitstagen. Urlaub zählt nur an diesen Tagen, Feiertage und
                Abwesenheiten werden mit den Stunden des jeweiligen Tages gutgeschrieben.
              </p>
            </div>
          )}

          {(mode === 'even' || mode === 'monthly') && (
            <>
              {mode === 'even' && (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="weekly-hours">Wochenstunden</Label>
                  <Input
                    id="weekly-hours"
                    inputMode="decimal"
                    className="w-32"
                    value={weeklyHours}
                    onChange={(event) => setWeeklyHours(event.target.value)}
                  />
                </div>
              )}
              <div className="flex flex-col gap-1.5">
                <Label>Arbeitstage</Label>
                <div className="flex gap-1.5">
                  {WEEKDAYS.map((label, day) => (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={weekdays.includes(day)}
                      onClick={() => toggleWeekday(day)}
                      className={cn(
                        'h-9 w-10 rounded-md border text-sm font-medium',
                        weekdays.includes(day)
                          ? 'border-slate-900 bg-slate-900 text-white'
                          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {mode === 'even' && dailyPreview && (
                  <p className="text-sm text-slate-500">
                    = {dailyPreview} h pro Arbeitstag. Feiertage und genehmigte Abwesenheiten an Arbeitstagen werden
                    mit diesem Tagessoll gutgeschrieben.
                  </p>
                )}
                {mode === 'monthly' && (
                  <p className="text-sm text-slate-500">
                    Jeden Monat dasselbe Soll, egal wie viele Arbeitstage der Monat hat. Es wird gleichmäßig auf die Arbeitstage
                    des Monats verteilt
                    {monthlyPreview ? ` (je nach Monat ${monthlyPreview.low}–${monthlyPreview.high} h pro Arbeitstag)` : ''}.
                    Feiertage und genehmigte Abwesenheiten werden mit dem Tagessoll des jeweiligen Monats gutgeschrieben.
                  </p>
                )}
              </div>
            </>
          )}

          {(shiftPlanningEnabled || shiftTemplateId !== '') && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="shift-template">Schichtvorlage (Uhrzeiten, optional)</Label>
            <select
              id="shift-template"
              className="h-9 w-72 rounded-md border border-slate-300 bg-white px-2 text-sm"
              value={shiftTemplateId}
              onChange={(event) => setShiftTemplateId(event.target.value)}
            >
              <option value="">Keine festen Uhrzeiten</option>
              {templateOptions.map((option) => (
                <option key={option.id} value={String(option.id)}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="text-sm text-slate-500">
              Beginn und Ende für Schichtplan, Pünktlichkeit und Ruhezeit-Prüfung. Das Soll bleibt das des
              Arbeitszeitmodells.
            </p>
          </div>
          )}

          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">Pause</legend>
            <div className="flex flex-wrap gap-2 text-sm">
              {(
                [
                  ['rules', templateBreak ? 'Wie Schichtvorlage' : 'Wie Pausenregeln'],
                  ['minutes', 'Feste Minuten'],
                  ['window', 'Feste Uhrzeit'],
                ] as const
              ).map(([kind, label]) => (
                <Button
                  key={kind}
                  type="button"
                  size="sm"
                  variant={breakKind === kind ? 'default' : 'outline'}
                  aria-pressed={breakKind === kind}
                  onClick={() => setBreakKind(kind)}
                >
                  {label}
                </Button>
              ))}
            </div>
            {breakKind === 'minutes' && (
              <div className="flex items-center gap-2">
                <Input
                  id="break-minutes"
                  aria-label="Pausenminuten"
                  inputMode="numeric"
                  className="w-24"
                  value={breakMinutes}
                  onChange={(event) => setBreakMinutes(event.target.value)}
                />
                <span className="text-sm text-slate-600">Minuten ab</span>
                <Input
                  aria-label="Pause ab Stunden"
                  inputMode="decimal"
                  className="w-20"
                  placeholder="0"
                  value={breakAfterHours}
                  onChange={(event) => setBreakAfterHours(event.target.value)}
                />
                <span className="text-sm text-slate-600">Std. Arbeit (leer = ab der ersten Minute), auch ohne Stempelung</span>
              </div>
            )}
            {breakKind === 'window' && (
              <div className="flex items-center gap-2">
                <Input
                  aria-label="Pause von"
                  type="time"
                  className="w-32"
                  value={breakStart}
                  onChange={(event) => setBreakStart(event.target.value)}
                />
                <span className="text-sm text-slate-600">bis</span>
                <Input
                  aria-label="Pause bis"
                  type="time"
                  className="w-32"
                  value={breakEnd}
                  onChange={(event) => setBreakEnd(event.target.value)}
                />
              </div>
            )}
            <p className="text-sm text-slate-500">
              {breakKind === 'rules'
                ? templateBreak
                  ? `Es gilt die Pause der Schichtvorlage (${templateBreak}).`
                  : 'Es gelten die Pausenregeln (gesetzliche Staffel und ggf. feste Pausen des Betriebs).'
                : breakKind === 'minutes'
                  ? 'Gestempelte Pausen zählen mit; nur was fehlt, wird abgezogen.'
                  : 'Abgezogen wird, soweit der Mitarbeiter in dieser Zeit da war.'}{' '}
              Die gesetzliche Pause gilt immer mindestens.
            </p>
          </fieldset>

          <CoreTimeFields value={coreTime} onChange={setCoreTime} />

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="valid-from">Gültig ab</Label>
            <Input
              id="valid-from"
              type="date"
              className="w-44"
              value={validFrom}
              onChange={(event) => setValidFrom(event.target.value)}
            />
            <p className="text-sm text-slate-500">
              {editing
                ? 'Ändert diese Fassung rückwirkend (Soll und Salden werden neu berechnet). Ein früherer Beginn kürzt die vorherige Fassung, ein späterer verlängert sie.'
                : 'Gilt ab diesem Tag und ersetzt alles ab dann (auch rückwirkend, solange der Monat nicht abgeschlossen ist). Die vorherige Fassung endet am Vortag.'}
            </p>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
          {saved && <p className="text-sm text-emerald-600">Arbeitszeitmodell gespeichert.</p>}

          <div className="flex gap-2">
            <Button
              type="submit"
              disabled={
                setModel.isPending ||
                updateVersion.isPending ||
                !hoursValid ||
                !breakValid ||
                !coreTimeValid(coreTime) ||
                ((mode === 'even' || mode === 'monthly') && weekdays.length === 0) ||
                !validFrom
              }
            >
              {setModel.isPending || updateVersion.isPending ? 'Speichere…' : 'Speichern'}
            </Button>
            {editing ? (
              <Button type="button" variant="outline" onClick={stopEditing}>
                Bearbeitung abbrechen
              </Button>
            ) : model?.configured && (
              <Button type="button" variant="outline" onClick={loadCurrent}>
                Zurücksetzen
              </Button>
            )}
          </div>
        </form>
      ) : (
        <p className="text-sm text-slate-500">Änderungen am Arbeitszeitmodell sind Admin/HR vorbehalten.</p>
      )}

      {(historyQuery.data?.length ?? 0) > 0 && (
        <div className="rounded-md border border-slate-200 bg-white p-4 text-sm">
          <p className="mb-2 font-medium text-slate-900">Verlauf</p>
          <div className="flex flex-col divide-y divide-slate-100">
            {historyQuery.data!.map((version) => (
              <div key={version.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
                <span className="w-48 font-medium text-slate-800">{formatRange(version)}</span>
                <span className="flex-1 text-slate-600">{describeVersion(version)}</span>
                {canEdit && (
                  <span className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => startEditing(version)}>
                      Bearbeiten
                    </Button>
                    <Button size="sm" variant="ghost" className="text-red-600" onClick={() => void handleDelete(version)}>
                      Löschen
                    </Button>
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function templateOptionLabel(template: { name: string; start_time: string | null; end_time: string | null }): string {
  return template.start_time && template.end_time
    ? `${template.name} (${hhmm(template.start_time)}–${hhmm(template.end_time)})`
    : template.name
}

function formatRange(version: WorkTimeModelVersion): string {
  return `${formatDate(version.valid_from)} – ${version.valid_to ? formatDate(version.valid_to) : 'heute'}`
}

function describeVersion(version: WorkTimeModelVersion): string {
  const core = coreTimeLabel(version)
  return describeTarget(version) + breakLabel(version) + shiftLabel(version) + (core ? `, ${core}` : '')
}

function describeTarget(version: WorkTimeModelVersion): string {
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

/** Aktuell gültige Fassung: Soll, Uhrzeiten, Pause und Kernzeit (auch lesend, z. B. im Schichtplan). */
export function WorkTimeModelSummary({ model, loading }: { model: WorkTimeModel | undefined; loading?: boolean }) {
  const core = model ? coreTimeLabel(model) : ''
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 text-sm text-slate-700">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium text-slate-900">Aktuell gültig</p>
        {model?.configured && <p className="text-slate-500">seit {model.valid_from ? formatDate(model.valid_from) : '–'}</p>}
      </div>
      {loading && <p className="text-slate-500">Lädt…</p>}
      {model && !model.configured && (
        <p className="text-slate-500">
          Noch kein Arbeitszeitmodell hinterlegt – ohne Modell gibt es kein Soll und jeder Tag gilt als „ohne Plan“.
        </p>
      )}
      {model?.configured && (
        <>
          <CurrentModel model={model} />
          <div className="mt-2 flex flex-col gap-0.5 text-slate-500">
            {model.shift_template_name && <p>Uhrzeiten: {shiftLabel(model).replace(', Schicht ', 'Schicht ')}</p>}
            <p>
              Pause:{' '}
              {breakLabel(model)
                ? `${breakLabel(model).replace(', Pause ', '')}${model.break_from_template ? ' (laut Schichtvorlage)' : ''}`
                : 'wie Pausenregeln'}
            </p>
            <p>Kernarbeitszeit: {core || 'wie in den Einstellungen'}</p>
            {model.target_from_template && (
              <p className="text-amber-700">
                Das Soll kommt bisher aus der Schichtvorlage „{model.shift_template_name}“ (ältere Zuordnung) und folgt
                deren Änderungen. Beim nächsten Speichern hier wird es fest ins Arbeitszeitmodell übernommen.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

/** Übersicht des gültigen Modells: Art, Wochensoll und Soll je Wochentag. */
function CurrentModel({ model }: { model: WorkTimeModel }) {
  const perDay: (number | null)[] = WEEKDAYS.map((_, day) => {
    if (model.flexible) return null
    if (model.day_minutes) return model.day_minutes[day] ?? 0
    return model.weekdays.includes(day) ? (model.daily_minutes ?? 0) : 0
  })
  if (model.on_demand) {
    return (
      <div className="mt-3 flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="text-2xl font-semibold text-slate-900">Nach Aufwand</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">ohne Soll</span>
        </div>
        <p className="text-slate-500">
          Abrechnung nach Ist-Stunden je Monat, kein Gleitzeitkonto.
          {model.monthly_cap_minutes
            ? ` Monatsgrenze ${formatHours(model.monthly_cap_minutes)} Std. – ab 90 % erscheint ein Hinweis unter „Zu klären“.`
            : ' Keine Monatsgrenze hinterlegt.'}
        </p>
      </div>
    )
  }
  if (model.monthly_minutes != null) {
    const days = workdaysInMonth(new Date(), model.weekdays)
    return (
      <div className="mt-3 flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="text-2xl font-semibold text-slate-900">{formatHours(model.monthly_minutes)} Std.</span>
          <span className="text-slate-500">pro Monat</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">Monatsstunden (fest)</span>
        </div>
        <div className="grid grid-cols-7 gap-1.5">
          {WEEKDAYS.map((label, day) => {
            const workday = model.weekdays.includes(day)
            return (
              <div
                key={label}
                className={cn(
                  'flex flex-col items-center rounded-md border py-1.5',
                  workday ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-slate-200 bg-slate-50 text-slate-400',
                )}
              >
                <span className="text-xs font-medium">{label}</span>
                <span className="text-sm font-semibold">{workday ? 'Arbeitstag' : 'frei'}</span>
              </div>
            )
          })}
        </div>
        {days > 0 && (
          <p className="text-slate-500">
            Diesen Monat {days} Arbeitstage = {formatHours(Math.round(model.monthly_minutes / days))} Std. pro Tag. Das Tagessoll
            ändert sich mit der Zahl der Arbeitstage, die Monatssumme bleibt gleich.
          </p>
        )}
      </div>
    )
  }
  const kind = model.flexible
    ? 'Flexibel ohne feste Tage'
    : model.uneven
      ? 'Stunden je Wochentag'
      : 'Gleichmäßig verteilt'

  return (
    <div className="mt-3 flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-2xl font-semibold text-slate-900">
          {model.weekly_minutes != null ? `${formatHours(model.weekly_minutes)} Std.` : '–'}
        </span>
        <span className="text-slate-500">pro Woche</span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">{kind}</span>
      </div>
      {model.flexible ? (
        <p className="text-slate-500">
          Keine festen Arbeitstage – abgerechnet wird je Woche. Feiertage und Abwesenheiten Mo–Fr zählen mit{' '}
          {model.weekly_minutes != null ? `${formatHours(Math.round(model.weekly_minutes / 5))} Std.` : 'einem Fünftel'}.
        </p>
      ) : (
        <div className="grid grid-cols-7 gap-1.5">
          {WEEKDAYS.map((label, day) => {
            const minutes = perDay[day] ?? 0
            return (
              <div
                key={label}
                className={cn(
                  'flex flex-col items-center rounded-md border py-1.5',
                  minutes > 0 ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-slate-200 bg-slate-50 text-slate-400',
                )}
              >
                <span className="text-xs font-medium">{label}</span>
                <span className="text-sm font-semibold">{minutes > 0 ? `${formatHours(minutes)} h` : 'frei'}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
