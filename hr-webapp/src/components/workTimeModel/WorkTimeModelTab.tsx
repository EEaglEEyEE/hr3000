import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
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
  type WorkTimeModelSetRequest,
  type WorkTimeModelVersion,
} from '../../api/queries/workTimeModel'
import { useAssignWorkTimeProfileMutation, useWorkTimeProfilesQuery } from '../../api/queries/workTimeProfiles'
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
import { BreakWindowsEditor, breakWindowsValid, type BreakWindow } from './BreakWindowsEditor'
import {
  DEFAULT_FLEX_FRAME,
  FlexFrameFields,
  flexFrameFromApi,
  flexFramePayload,
  flexFrameValid,
  type FlexFrameValue,
} from './FlexFrameFields'
import {
  breakLabel,
  describeVersion,
  flexFrameLabel,
  formatHours,
  formatRange,
  hhmm,
  shiftLabel,
  WEEKDAYS,
  type ModelSource,
} from './modelText'

const WORKWEEK = [0, 1, 2, 3, 4]

function toIsoDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
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

/** Was das Formular liefert (ohne „gültig ab“); die Toleranz nur bei Modellen. */
export type ModelFormPayload = Omit<WorkTimeModelSetRequest, 'valid_from'> & {
  late_tolerance_minutes?: number | null
}

/** Formular eines Arbeitszeitmodells – am Mitarbeiter (neue Fassung bzw. nachträgliche Änderung) und
 * für Arbeitszeitmodelle (dazu die Toleranz). Wechselt `loadToken`, wird es mit
 * `source` neu vorbelegt; ändert sich nur `source` (z. B. nach dem Speichern), werden die Werte
 * übernommen. */
export function WorkTimeModelForm({
  source,
  loadToken,
  initialValidFrom,
  heading,
  highlighted = false,
  withValidFrom = true,
  validFromHint,
  withTolerance = false,
  children,
  extraValid = true,
  pending,
  savedText,
  onSubmit,
  onCancel,
  cancelLabel = 'Abbrechen',
}: {
  source: ModelSource | null
  loadToken: string
  initialValidFrom?: string
  heading: string
  highlighted?: boolean
  withValidFrom?: boolean
  validFromHint?: string
  /** Toleranz der Pünktlichkeitsprüfung (nur Arbeitszeitmodelle). */
  withTolerance?: boolean
  /** Zusätzliche Felder oben im Formular (z. B. Name eines Modells). */
  children?: ReactNode
  extraValid?: boolean
  pending: boolean
  savedText: string
  onSubmit: (payload: ModelFormPayload, validFrom: string) => Promise<void>
  onCancel?: () => void
  cancelLabel?: string
}) {
  const templatesQuery = useShiftTemplatesQuery()
  // Schichtvorlagen gibt es mit Schichtplanung (Einstellungen); eine schon zugeordnete bleibt sichtbar.
  const shiftPlanningEnabled = useFeaturesQuery().data?.shift_planning_enabled ?? false
  const templates = templatesQuery.data ?? []

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
  // Feste Pausenzeiten (bis zu MAX_BREAK_WINDOWS, z. B. Frühstück und Mittag)
  const [breakWindows, setBreakWindows] = useState<BreakWindow[]>([{ start: '12:00', end: '12:30' }])
  // Schichtvorlage nur für die Uhrzeiten ('' = keine festen Uhrzeiten)
  const [shiftTemplateId, setShiftTemplateId] = useState('')
  // Vorlage der geladenen Fassung (auch eine alte, archivierte Fassung einer Vorlage)
  const [loadedShift, setLoadedShift] = useState<{ id: number; name: string; breakFromTemplate: boolean } | null>(null)
  const [coreTime, setCoreTime] = useState<CoreTimeValue>(DEFAULT_CORE_TIME)
  const [frame, setFrame] = useState<FlexFrameValue>(DEFAULT_FLEX_FRAME)
  // Nur Modelle: Toleranz der Pünktlichkeitsprüfung ('' = wie Einstellungen)
  const [tolerance, setTolerance] = useState('')
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
      : breakWindowsValid(breakWindows))
  const breakPayload =
    breakKind === 'minutes'
      ? { break_minutes: breakMinutesNumber, ...(breakAfter ? { break_after_hours: breakAfter } : {}) }
      : breakKind === 'window'
        ? breakWindows.length === 1
          ? { break_start: breakWindows[0].start, break_end: breakWindows[0].end }
          : { break_windows: breakWindows }
        : {}
  const toleranceNumber = tolerance.trim() ? Number(tolerance) : null
  const toleranceValid = toleranceNumber === null || (Number.isInteger(toleranceNumber) && toleranceNumber >= 0 && toleranceNumber <= 120)
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

  // Vorbelegen: bei neuem loadToken immer (samt „gültig ab“), sonst einmal je geladenem Stand.
  const loadedToken = useRef<string | null>(null)
  const loadedSource = useRef<string | null>(null)
  // Nach dem Speichern einer nachträglichen Änderung wechselt der Token – die Meldung bleibt stehen.
  const keepNotice = useRef(false)
  useEffect(() => {
    const sourceKey = source ? JSON.stringify(source) : null
    if (loadToken !== loadedToken.current) {
      loadedToken.current = loadToken
      loadedSource.current = sourceKey
      if (source) loadFrom(source)
      setValidFrom(initialValidFrom ?? toIsoDate(new Date()))
      if (!keepNotice.current) {
        setError(null)
        setSaved(false)
      }
      keepNotice.current = false
      return
    }
    if (source && sourceKey !== loadedSource.current) {
      loadedSource.current = sourceKey
      loadFrom(source)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadToken, source])

  function loadFrom(source: ModelSource) {
    if (source.break_minutes && !source.break_from_template) {
      setBreakKind('minutes')
      setBreakMinutes(String(source.break_minutes))
      setBreakAfterHours(source.break_after_minutes ? decimal(source.break_after_minutes / 60) : '')
    } else if ((source.break_windows?.length || (source.break_start && source.break_end)) && !source.break_from_template) {
      setBreakKind('window')
      setBreakWindows(
        source.break_windows?.length
          ? source.break_windows.map((w) => ({ start: hhmm(w.start), end: hhmm(w.end) }))
          : [{ start: hhmm(source.break_start), end: hhmm(source.break_end) }],
      )
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
    setFrame(flexFrameFromApi(source))
    setTolerance(source.late_tolerance_minutes != null ? String(source.late_tolerance_minutes) : '')
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSaved(false)
    const modelPayload =
      mode === 'onDemand'
        ? { on_demand: true, flexible: false, monthly_cap_hours: cap }
        : mode === 'perDay'
        ? { daily_hours: parsedDaily, flexible: false, on_demand: false }
        : mode === 'monthly'
        ? { monthly_hours: monthly, weekdays, flexible: false, on_demand: false }
        : mode === 'flex'
          ? { weekly_hours: hours, flexible: true, on_demand: false }
          : { weekly_hours: hours, weekdays, flexible: false, on_demand: false }
    const framePayload = { ...flexFramePayload(frame), ...(withTolerance ? { late_tolerance_minutes: toleranceNumber } : {}) }
    const payload: ModelFormPayload = {
      ...modelPayload,
      ...breakPayload,
      shift_template_id: shiftTemplateId ? Number(shiftTemplateId) : null,
      ...coreTimePayload(coreTime),
      ...framePayload,
    }
    try {
      await onSubmit(payload, validFrom)
      keepNotice.current = !!onCancel
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
    <form
      className={cn(
        'flex flex-col gap-4 rounded-md border bg-white p-4',
        highlighted ? 'border-amber-300 ring-1 ring-amber-200' : 'border-slate-200',
      )}
      onSubmit={handleSubmit}
    >
      <p className="font-medium text-slate-900">{heading}</p>

      {children}

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
            Kein Soll und kein Überstundenkonto: jede Stempelung zählt als Ist-Zeit, Monate ohne Einsatz sind kein Minus,
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
          className="h-9 w-72 max-w-full rounded-md border border-slate-300 bg-white px-2 text-sm"
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
        {breakKind === 'window' && <BreakWindowsEditor windows={breakWindows} onChange={setBreakWindows} />}
        <p className="text-sm text-slate-500">
          {breakKind === 'rules'
            ? templateBreak
              ? `Es gilt die Pause der Schichtvorlage (${templateBreak}).`
              : 'Es gelten die Pausenregeln (gesetzliche Staffel und ggf. feste Pausen des Betriebs).'
            : breakKind === 'minutes'
              ? 'Gestempelte Pausen zählen mit; nur was fehlt, wird abgezogen.'
              : 'Abgezogen wird jede Pausenzeit, soweit der Mitarbeiter in ihr da war.'}{' '}
          Die gesetzliche Pause gilt immer mindestens.
        </p>
      </fieldset>

      <CoreTimeFields value={coreTime} onChange={setCoreTime} />

      <FlexFrameFields value={frame} onChange={setFrame} />

      {withTolerance && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="late-tolerance">Toleranz der Pünktlichkeitsprüfung (Minuten)</Label>
          <Input
            id="late-tolerance"
            inputMode="numeric"
            className="w-24"
            placeholder="wie Einst."
            value={tolerance}
            onChange={(event) => setTolerance(event.target.value)}
          />
          <p className="text-sm text-slate-500">Leer = wie in den Einstellungen (0–120 Minuten).</p>
        </div>
      )}

      {withValidFrom && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="valid-from">Gültig ab</Label>
          <Input
            id="valid-from"
            type="date"
            className="w-44"
            value={validFrom}
            onChange={(event) => setValidFrom(event.target.value)}
          />
          {validFromHint && <p className="text-sm text-slate-500">{validFromHint}</p>}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
      {saved && <p className="text-sm text-emerald-600">{savedText}</p>}

      <div className="flex gap-2">
        <Button
          type="submit"
          disabled={
            pending ||
            !extraValid ||
            !hoursValid ||
            !breakValid ||
            !coreTimeValid(coreTime) ||
            !flexFrameValid(frame) ||
            (withTolerance && !toleranceValid) ||
            ((mode === 'even' || mode === 'monthly') && weekdays.length === 0) ||
            (withValidFrom && !validFrom)
          }
        >
          {pending ? 'Speichere…' : 'Speichern'}
        </Button>
        {onCancel ? (
          <Button type="button" variant="outline" onClick={onCancel}>
            {cancelLabel}
          </Button>
        ) : source && (
          <Button type="button" variant="outline" onClick={() => loadFrom(source)}>
            Zurücksetzen
          </Button>
        )}
      </div>
    </form>
  )
}

/** Reiter „Arbeitszeit“ am Mitarbeiter: aktuelles Modell, Modell zuweisen oder individuell eintragen, Verlauf. */
export function WorkTimeModelTab({ employeeId, canEdit }: { employeeId: number; canEdit: boolean }) {
  const modelQuery = useWorkTimeModelQuery(employeeId)
  const setModel = useSetWorkTimeModelMutation(employeeId)
  const updateVersion = useUpdateWorkTimeModelVersionMutation(employeeId)
  const deleteVersion = useDeleteWorkTimeModelVersionMutation(employeeId)
  const historyQuery = useWorkTimeModelHistoryQuery(employeeId)
  const model = modelQuery.data
  // Nachträgliche Änderung einer bestehenden Fassung statt neuer Fassung ab Stichtag
  const [editing, setEditing] = useState<WorkTimeModelVersion | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const formRef = useRef<HTMLDivElement>(null)

  function startEditing(version: WorkTimeModelVersion) {
    setEditing(version)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  async function handleDelete(version: WorkTimeModelVersion) {
    if (!window.confirm(`Fassung ab ${formatDate(version.valid_from)} löschen? Die vorherige Fassung gilt dann weiter.`)) return
    setHistoryError(null)
    try {
      await deleteVersion.mutateAsync(version.id)
      if (editing?.id === version.id) setEditing(null)
    } catch (err) {
      setHistoryError(err instanceof ApiError ? err.message : 'Löschen fehlgeschlagen.')
    }
  }

  async function handleSubmit(payload: ModelFormPayload, validFrom: string) {
    if (editing) {
      await updateVersion.mutateAsync({ versionId: editing.id, payload: { ...payload, valid_from: validFrom } })
      setEditing(null)
    } else {
      await setModel.mutateAsync({ ...payload, valid_from: validFrom })
    }
  }

  const heading = editing
    ? `Fassung ${formatRange(editing)} nachträglich ändern${
        editing.profile_name ? ` (danach individuell statt Modell „${editing.profile_name}“)` : ''
      }`
    : model?.profile_name
      ? 'Individuell eintragen ab Stichtag (statt zugewiesenem Modell)'
      : 'Neues Arbeitszeitmodell ab Stichtag'

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <WorkTimeModelSummary model={model} loading={modelQuery.isLoading} />

      {canEdit ? (
        <>
          <ProfileAssignCard employeeId={employeeId} model={model} />
          <div ref={formRef}>
            <WorkTimeModelForm
              source={editing ?? (model?.configured ? model : null)}
              loadToken={editing ? `version-${editing.id}` : 'current'}
              initialValidFrom={editing?.valid_from}
              heading={heading}
              highlighted={editing !== null}
              validFromHint={
                editing
                  ? 'Ändert diese Fassung rückwirkend (Soll und Salden werden neu berechnet). Ein früherer Beginn kürzt die vorherige Fassung, ein späterer verlängert sie.'
                  : 'Gilt ab diesem Tag und ersetzt alles ab dann (auch rückwirkend, solange der Monat nicht abgeschlossen ist). Die vorherige Fassung endet am Vortag.'
              }
              pending={setModel.isPending || updateVersion.isPending}
              savedText="Arbeitszeitmodell gespeichert."
              onSubmit={handleSubmit}
              onCancel={editing ? () => setEditing(null) : undefined}
              cancelLabel="Bearbeitung abbrechen"
            />
          </div>
        </>
      ) : (
        <p className="text-sm text-slate-500">Änderungen am Arbeitszeitmodell sind Admin/HR vorbehalten.</p>
      )}

      {(historyQuery.data?.length ?? 0) > 0 && (
        <div className="rounded-md border border-slate-200 bg-white p-4 text-sm">
          <p className="mb-2 font-medium text-slate-900">Verlauf</p>
          {historyError && <p className="mb-2 text-red-600">{historyError}</p>}
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

/** Arbeitszeitmodell ab Stichtag zuweisen – nur sichtbar, wenn es Modelle gibt (oder eines zugewiesen ist). */
function ProfileAssignCard({ employeeId, model }: { employeeId: number; model: WorkTimeModel | undefined }) {
  const profilesQuery = useWorkTimeProfilesQuery()
  const assign = useAssignWorkTimeProfileMutation(employeeId)
  const profiles = profilesQuery.data ?? []
  const [profileId, setProfileId] = useState('')
  const [validFrom, setValidFrom] = useState(() => toIsoDate(new Date()))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  if (profiles.length === 0 && !model?.profile_id) return null

  async function handleAssign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSaved(false)
    try {
      await assign.mutateAsync({ profile_id: Number(profileId), valid_from: validFrom })
      setSaved(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Zuweisen fehlgeschlagen.')
    }
  }

  return (
    <form className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleAssign}>
      <p className="font-medium text-slate-900">Arbeitszeitmodell zuweisen</p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="assign-profile">Arbeitszeitmodell</Label>
          <select
            id="assign-profile"
            className="h-9 w-72 max-w-full rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={profileId}
            onChange={(event) => setProfileId(event.target.value)}
          >
            <option value="">Bitte wählen</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={String(profile.id)}>
                {profile.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="assign-valid-from">Modell gültig ab</Label>
          <Input
            id="assign-valid-from"
            type="date"
            className="w-44"
            value={validFrom}
            onChange={(event) => setValidFrom(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={!profileId || !validFrom || assign.isPending}>
          {assign.isPending ? 'Weise zu…' : 'Modell zuweisen'}
        </Button>
      </div>
      <p className="text-sm text-slate-500">
        Soll, Arbeitstage, Pause, Kernzeit, Gleitzeit-Rahmen und Toleranz kommen dann aus dem Modell und folgen automatisch
        dessen Änderungen. Ersetzt alles ab diesem Tag; wer eigene Werte braucht, trägt sie unten individuell ein.
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {saved && <p className="text-sm text-emerald-600">Arbeitszeitmodell zugewiesen.</p>}
    </form>
  )
}

function templateOptionLabel(template: { name: string; start_time: string | null; end_time: string | null }): string {
  return template.start_time && template.end_time
    ? `${template.name} (${hhmm(template.start_time)}–${hhmm(template.end_time)})`
    : template.name
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
            {flexFrameLabel(model) && <p>Gleitzeit-Rahmen: {flexFrameLabel(model)}</p>}
            {model.late_tolerance_minutes != null && <p>Toleranz der Pünktlichkeitsprüfung: {model.late_tolerance_minutes} Min.</p>}
            {model.profile_name && (
              <p className="text-slate-700">
                Arbeitszeitmodell „{model.profile_name}“ – Änderungen am Modell gelten automatisch.
              </p>
            )}
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
          Abrechnung nach Ist-Stunden je Monat, kein Überstundenkonto.
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
