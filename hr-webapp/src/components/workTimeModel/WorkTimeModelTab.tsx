import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import {
  useDeleteWorkTimeModelVersionMutation,
  useSetWorkTimeModelMutation,
  useUpdateWorkTimeModelVersionMutation,
  useWorkTimeModelHistoryQuery,
  useWorkTimeModelQuery,
  type WorkTimeModelVersion,
} from '../../api/queries/workTimeModel'
import { formatDate } from '../../lib/format'
import { cn } from '../../lib/utils'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const WORKWEEK = [0, 1, 2, 3, 4]

function toIsoDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function formatHours(minutes: number): string {
  return (minutes / 60).toLocaleString('de-DE', { maximumFractionDigits: 2 })
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

export function WorkTimeModelTab({ employeeId, canEdit }: { employeeId: number; canEdit: boolean }) {
  const modelQuery = useWorkTimeModelQuery(employeeId)
  const setModel = useSetWorkTimeModelMutation(employeeId)
  const updateVersion = useUpdateWorkTimeModelVersionMutation(employeeId)
  const deleteVersion = useDeleteWorkTimeModelVersionMutation(employeeId)
  const historyQuery = useWorkTimeModelHistoryQuery(employeeId)
  const model = modelQuery.data
  // Nachträgliche Änderung einer bestehenden Fassung statt neuer Fassung ab Stichtag
  const [editing, setEditing] = useState<WorkTimeModelVersion | null>(null)
  const formRef = useRef<HTMLFormElement>(null)

  const [weeklyHours, setWeeklyHours] = useState('40')
  const [weekdays, setWeekdays] = useState<number[]>(WORKWEEK)
  // "even" = Wochenstunden gleichmäßig verteilt; "perDay" = Stunden je Wochentag (Teilzeit).
  // "flex" = Wochensoll ohne feste Tage; "onDemand" = nach Aufwand ohne Soll (Aushilfe).
  // "monthly" = festes Monatssoll, auf die Arbeitstage des jeweiligen Monats verteilt.
  const [mode, setMode] = useState<'even' | 'monthly' | 'perDay' | 'flex' | 'onDemand'>('even')
  const [monthlyHours, setMonthlyHours] = useState('')
  const [capHours, setCapHours] = useState('')
  const [dailyHours, setDailyHours] = useState<string[]>(['8', '8', '8', '8', '8', '', ''])
  const [validFrom, setValidFrom] = useState(() => toIsoDate(new Date()))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

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
  const dailyPreview = hoursValid && weekdays.length > 0 ? formatHours(Math.round((hours * 60) / weekdays.length)) : null
  // Monatssoll: Tagessoll je nach Monat zwischen (Monat mit den meisten) und (Monat mit den wenigsten Arbeitstagen).
  const monthlyPreview =
    mode === 'monthly' && hoursValid && weekdays.length > 0
      ? {
          low: formatHours(Math.round((monthly * 60) / (4 * weekdays.length + Math.min(weekdays.length, 3)))),
          high: formatHours(Math.round((monthly * 60) / (4 * weekdays.length))),
        }
      : null

  function toggleWeekday(day: number) {
    setWeekdays((current) =>
      current.includes(day) ? current.filter((value) => value !== day) : [...current, day].sort(),
    )
  }

  // Formular immer mit dem aktuell gültigen Modell vorbelegen (einmal je geladenem Stand).
  const loadedFor = useRef<string | null>(null)
  useEffect(() => {
    const key = model
      ? JSON.stringify([model.valid_from, model.weekly_minutes, model.monthly_minutes, model.day_minutes, model.on_demand, model.monthly_cap_minutes])
      : null
    if (!model?.configured || key === loadedFor.current) return
    loadedFor.current = key
    loadCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model])

  function loadCurrent() {
    if (!model?.configured) return
    loadFrom(model)
  }

  function loadFrom(source: {
    weekly_minutes: number | null
    weekdays: number[]
    day_minutes?: number[] | null
    flexible?: boolean
    uneven?: boolean
    on_demand?: boolean
    monthly_cap_minutes?: number | null
    monthly_minutes?: number | null
  }) {
    if (source.on_demand) {
      setMode('onDemand')
      setCapHours(source.monthly_cap_minutes ? String(source.monthly_cap_minutes / 60).replace('.', ',') : '')
      return
    }
    if (source.monthly_minutes != null) {
      setMode('monthly')
      setMonthlyHours(String(source.monthly_minutes / 60).replace('.', ','))
      if (source.weekdays.length > 0) setWeekdays(source.weekdays)
      return
    }
    if (source.weekly_minutes === null) return
    setWeeklyHours(String(source.weekly_minutes / 60))
    if (source.weekdays.length > 0) setWeekdays(source.weekdays)
    if (source.day_minutes) {
      setDailyHours(source.day_minutes.map((m) => (m > 0 ? String(m / 60).replace('.', ',') : '')))
    }
    setMode(source.flexible ? 'flex' : source.uneven ? 'perDay' : 'even')
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
    const payload =
      mode === 'onDemand'
        ? { on_demand: true, flexible: false, monthly_cap_hours: cap, valid_from: validFrom }
        : mode === 'perDay'
        ? { daily_hours: parsedDaily, flexible: false, on_demand: false, valid_from: validFrom }
        : mode === 'monthly'
        ? { monthly_hours: monthly, weekdays, flexible: false, on_demand: false, valid_from: validFrom }
        : mode === 'flex'
          ? { weekly_hours: hours, flexible: true, on_demand: false, valid_from: validFrom }
          : { weekly_hours: hours, weekdays, flexible: false, on_demand: false, valid_from: validFrom }
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
      <div className="rounded-md border border-slate-200 bg-white p-4 text-sm text-slate-700">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="font-medium text-slate-900">Aktuell gültig</p>
          {model?.configured && (
            <p className="text-slate-500">
              seit {model.valid_from ? formatDate(model.valid_from) : '–'}
              {!model.is_work_time_model && ' · über eine Schichtvorlage gesteuert (siehe Schichtplanung)'}
            </p>
          )}
        </div>
        {modelQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
        {model && !model.configured && (
          <p className="text-slate-500">
            Noch kein Arbeitszeitmodell hinterlegt – ohne Modell gibt es kein Soll und jeder Tag gilt als
            „ohne Plan“.
          </p>
        )}
        {model?.configured && <CurrentModel model={model} />}
      </div>

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

          <div className="flex flex-wrap gap-2 text-sm">
            <Button type="button" size="sm" variant={mode === 'even' ? 'default' : 'outline'} onClick={() => setMode('even')}>
              Gleichmäßig verteilt
            </Button>
            <Button type="button" size="sm" variant={mode === 'monthly' ? 'default' : 'outline'} onClick={() => setMode('monthly')}>
              Monatsstunden (fest)
            </Button>
            <Button type="button" size="sm" variant={mode === 'perDay' ? 'default' : 'outline'} onClick={() => setMode('perDay')}>
              Stunden je Wochentag (Teilzeit)
            </Button>
            <Button type="button" size="sm" variant={mode === 'flex' ? 'default' : 'outline'} onClick={() => setMode('flex')}>
              Flexibel ohne feste Tage
            </Button>
            <Button type="button" size="sm" variant={mode === 'onDemand' ? 'default' : 'outline'} onClick={() => setMode('onDemand')}>
              Nach Aufwand (Aushilfe)
            </Button>
          </div>

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
                und es gibt keine „fehlt“- oder „außerplanmäßig“-Tage. Abgerechnet werden die Ist-Stunden je Monat
                (Monatsbericht, Lohn-Export). Mit Monatsgrenze erscheint ab 90 % ein Hinweis unter „Zu klären“. Urlaub und
                Feiertagsbezahlung laufen über die Lohnabrechnung.
              </p>
            </div>
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

          {(mode === 'even' || mode === 'monthly') && (
          <>
          {mode === 'even' ? (
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
          ) : (
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
            ) : model?.configured && (model.weekly_minutes !== null || model.monthly_minutes != null || model.on_demand) && (
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
                {canEdit && version.is_work_time_model && (
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

function formatRange(version: WorkTimeModelVersion): string {
  return `${formatDate(version.valid_from)} – ${version.valid_to ? formatDate(version.valid_to) : 'heute'}`
}

function describeVersion(version: WorkTimeModelVersion): string {
  if (!version.is_work_time_model) return `Schichtvorlage „${version.template_name}“`
  if (version.on_demand) {
    return `Nach Aufwand ohne Soll${version.monthly_cap_minutes ? `, Monatsgrenze ${formatHours(version.monthly_cap_minutes)} h` : ''}`
  }
  if (version.monthly_minutes != null) {
    return `${formatHours(version.monthly_minutes)} h/Monat an ${version.weekdays.map((d) => WEEKDAYS[d]).join(', ')}`
  }
  const weekly = version.weekly_minutes !== null ? `${formatHours(version.weekly_minutes)} h/Woche` : ''
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

type WorkTimeModel = NonNullable<ReturnType<typeof useWorkTimeModelQuery>['data']>

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
          {model.weekly_minutes !== null ? `${formatHours(model.weekly_minutes)} Std.` : model.template_name}
        </span>
        <span className="text-slate-500">pro Woche</span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">{kind}</span>
      </div>
      {model.flexible ? (
        <p className="text-slate-500">
          Keine festen Arbeitstage – abgerechnet wird je Woche. Feiertage und Abwesenheiten Mo–Fr zählen mit{' '}
          {model.weekly_minutes !== null ? `${formatHours(Math.round(model.weekly_minutes / 5))} Std.` : 'einem Fünftel'}.
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
