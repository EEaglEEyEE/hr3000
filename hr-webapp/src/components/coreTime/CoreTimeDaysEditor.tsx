/** Kernzeit je Wochentag (Mo..So): je Tag von–bis oder „keine“. Genutzt in den Einstellungen und
 *  bei der eigenen Kernzeit eines Mitarbeiters. */
import { Input } from '../ui/input'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

export type CoreTimeDay = { start: string; end: string } | null

/** Vorschlag beim Einschalten: Mo–Fr die bisherige Kernzeit, Wochenende ohne. */
export function initialCoreTimeDays(start: string, end: string): CoreTimeDay[] {
  return WEEKDAYS.map((_, day) => (day < 5 ? { start: start || '09:00', end: end || '15:00' } : null))
}

/** Aus der API (Zeiten mit Sekunden) in Formularwerte HH:MM. */
export function coreTimeDaysFromApi(days: ({ start: string; end: string } | null)[] | null | undefined): CoreTimeDay[] | null {
  return days ? days.map((d) => (d ? { start: d.start.slice(0, 5), end: d.end.slice(0, 5) } : null)) : null
}

export function coreTimeDaysValid(days: CoreTimeDay[]): boolean {
  return days.every((d) => d === null || (d.start !== '' && d.end !== '' && d.start < d.end))
}

export function CoreTimeDaysEditor({ days, onChange }: { days: CoreTimeDay[]; onChange: (days: CoreTimeDay[]) => void }) {
  function set(index: number, value: CoreTimeDay) {
    onChange(days.map((d, i) => (i === index ? value : d)))
  }
  return (
    <div className="flex flex-col gap-1.5">
      {WEEKDAYS.map((label, index) => {
        const day = days[index]
        return (
          <div key={label} className="flex flex-wrap items-center gap-2 text-sm">
            <label className="flex w-24 items-center gap-2">
              <input
                type="checkbox"
                aria-label={`${label} Kernzeit`}
                checked={day !== null}
                onChange={(e) => set(index, e.target.checked ? { start: '09:00', end: '15:00' } : null)}
              />
              {label}
            </label>
            {day ? (
              <>
                <Input
                  type="time"
                  aria-label={`${label} von`}
                  className="w-28"
                  value={day.start}
                  onChange={(e) => set(index, { ...day, start: e.target.value })}
                />
                <span className="text-slate-500">bis</span>
                <Input
                  type="time"
                  aria-label={`${label} bis`}
                  className="w-28"
                  value={day.end}
                  onChange={(e) => set(index, { ...day, end: e.target.value })}
                />
              </>
            ) : (
              <span className="text-slate-500">keine Kernzeit</span>
            )}
          </div>
        )
      })}
      {!coreTimeDaysValid(days) && <p className="text-xs text-red-600">Der Beginn muss jeweils vor dem Ende liegen.</p>}
    </div>
  )
}
