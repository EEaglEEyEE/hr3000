/** Zeitfenster je Wochentag (Mo..So): je Tag von–bis oder „keine“. Genutzt für die Kernzeit (Einstellungen,
 *  Arbeitszeitmodell) und für den Gleitzeit-Rahmen je Wochentag. */
import { Input } from '../ui/input'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

export type CoreTimeDay = { start: string; end: string } | null
export type DayWindow = CoreTimeDay

/** Vorschlag beim Einschalten: Mo–Fr das bisherige Fenster, Wochenende ohne. */
export function initialCoreTimeDays(start: string, end: string, fallback: { start: string; end: string } = { start: '09:00', end: '15:00' }): CoreTimeDay[] {
  return WEEKDAYS.map((_, day) => (day < 5 ? { start: start || fallback.start, end: end || fallback.end } : null))
}

/** Aus der API (Zeiten mit Sekunden) in Formularwerte HH:MM. */
export function coreTimeDaysFromApi(days: ({ start: string; end: string } | null)[] | null | undefined): CoreTimeDay[] | null {
  return days ? days.map((d) => (d ? { start: d.start.slice(0, 5), end: d.end.slice(0, 5) } : null)) : null
}

export function coreTimeDaysValid(days: CoreTimeDay[]): boolean {
  return days.every((d) => d === null || (d.start !== '' && d.end !== '' && d.start < d.end))
}

/** Kurzform, aufeinanderfolgende gleiche Tage zusammengefasst – z. B. „Mo–Do 07:00–19:00, Fr 07:00–14:00, Sa–So keiner“. */
export function describeDayWindows(days: DayWindow[], empty: string): string {
  const parts: string[] = []
  let index = 0
  while (index < days.length) {
    let last = index
    const same = (a: DayWindow, b: DayWindow) => (a === null ? b === null : b !== null && a.start === b.start && a.end === b.end)
    while (last + 1 < days.length && same(days[last + 1], days[index])) last++
    const span = last === index ? WEEKDAYS[index] : `${WEEKDAYS[index]}–${WEEKDAYS[last]}`
    const window = days[index]
    parts.push(window ? `${span} ${window.start}–${window.end}` : `${span} ${empty}`)
    index = last + 1
  }
  return parts.join(', ')
}

export function DayWindowsEditor({
  days,
  onChange,
  name,
  ariaPrefix = '',
  noneLabel,
  defaultWindow,
}: {
  days: DayWindow[]
  onChange: (days: DayWindow[]) => void
  /** Wofür die Fenster stehen, z. B. „Kernzeit“ (Beschriftung der Häkchen). */
  name: string
  /** Vorsatz der Beschriftung der Zeitfelder, damit zwei Editoren in einem Formular unterscheidbar sind. */
  ariaPrefix?: string
  noneLabel: string
  defaultWindow: { start: string; end: string }
}) {
  function set(index: number, value: DayWindow) {
    onChange(days.map((d, i) => (i === index ? value : d)))
  }
  return (
    <div className="flex flex-col gap-1.5">
      {WEEKDAYS.map((label, index) => {
        const day = days[index]
        return (
          // Raster statt Umbruch: die Zeitfelder schrumpfen mit, jeder Tag bleibt einzeilig (auch in schmalen Spalten).
          <div key={label} className="grid grid-cols-[3.25rem_minmax(0,7rem)_auto_minmax(0,7rem)] items-center justify-start gap-1.5 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label={`${label} ${name}`}
                checked={day !== null}
                onChange={(e) => set(index, e.target.checked ? { ...defaultWindow } : null)}
              />
              {label}
            </label>
            {day ? (
              <>
                <Input
                  type="time"
                  aria-label={`${ariaPrefix}${label} von`}
                  className="min-w-0 px-2"
                  value={day.start}
                  onChange={(e) => set(index, { ...day, start: e.target.value })}
                />
                <span className="text-slate-500">bis</span>
                <Input
                  type="time"
                  aria-label={`${ariaPrefix}${label} bis`}
                  className="min-w-0 px-2"
                  value={day.end}
                  onChange={(e) => set(index, { ...day, end: e.target.value })}
                />
              </>
            ) : (
              <span className="col-span-3 text-slate-500">{noneLabel}</span>
            )}
          </div>
        )
      })}
      {!coreTimeDaysValid(days) && <p className="text-xs text-red-600">Der Beginn muss jeweils vor dem Ende liegen.</p>}
    </div>
  )
}

export function CoreTimeDaysEditor({ days, onChange }: { days: CoreTimeDay[]; onChange: (days: CoreTimeDay[]) => void }) {
  return (
    <DayWindowsEditor
      days={days}
      onChange={onChange}
      name="Kernzeit"
      noneLabel="keine Kernzeit"
      defaultWindow={{ start: '09:00', end: '15:00' }}
    />
  )
}
