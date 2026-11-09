/** Feste Pausenzeiten eines Arbeitszeitmodells: eine oder mehrere (z. B. Frühstück 09:00–09:15 und Mittag
 *  12:00–12:30). Jede wird abgezogen, soweit der Mitarbeiter in ihr da war. */
import { X } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

export type BreakWindow = { start: string; end: string }

/** Höchstens so viele Pausenzeiten (wie MAX_BREAK_WINDOWS im Backend). */
export const MAX_BREAK_WINDOWS = 4

/** Jede Pausenzeit vollständig, Beginn vor Ende, keine Überschneidung (Reihenfolge egal). */
export function breakWindowsValid(windows: BreakWindow[]): boolean {
  if (windows.length === 0 || windows.length > MAX_BREAK_WINDOWS) return false
  if (!windows.every((w) => w.start !== '' && w.end !== '' && w.start < w.end)) return false
  const sorted = [...windows].sort((a, b) => a.start.localeCompare(b.start))
  return sorted.every((w, index) => index === 0 || sorted[index - 1].end <= w.start)
}

/** Vorschlag für eine weitere Pausenzeit: 15 Minuten nach dem Ende der letzten (sonst 09:00–09:15). */
export function nextBreakWindow(windows: BreakWindow[]): BreakWindow {
  const last = [...windows].sort((a, b) => a.start.localeCompare(b.start)).at(-1)
  if (!last || !last.end || last.end >= '23:00') return { start: '09:00', end: '09:15' }
  const [hours, minutes] = last.end.split(':').map(Number)
  const at = (offset: number) => {
    const total = Math.min(hours * 60 + minutes + offset, 23 * 60 + 59)
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
  }
  return { start: at(60), end: at(75) }
}

export function BreakWindowsEditor({ windows, onChange }: { windows: BreakWindow[]; onChange: (windows: BreakWindow[]) => void }) {
  function set(index: number, value: BreakWindow) {
    onChange(windows.map((w, i) => (i === index ? value : w)))
  }
  // Beschriftung der ersten Pausenzeit wie bisher („Pause von“), weitere nummeriert
  const label = (index: number, part: 'von' | 'bis') => (index === 0 ? `Pause ${part}` : `Pause ${index + 1} ${part}`)
  return (
    <div className="flex flex-col gap-1.5">
      {windows.map((window, index) => (
        // Raster: Zeitfelder schrumpfen mit, „Entfernen“ bleibt in der Zeile (auch am Handy)
        <div
          key={index}
          className="grid grid-cols-[minmax(0,8rem)_auto_minmax(0,8rem)_2.25rem] items-center justify-start gap-2"
        >
          <Input
            aria-label={label(index, 'von')}
            type="time"
            className="min-w-0 px-2"
            value={window.start}
            onChange={(event) => set(index, { ...window, start: event.target.value })}
          />
          <span className="text-sm text-slate-600">bis</span>
          <Input
            aria-label={label(index, 'bis')}
            type="time"
            className="min-w-0 px-2"
            value={window.end}
            onChange={(event) => set(index, { ...window, end: event.target.value })}
          />
          {windows.length > 1 ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label={`Pausenzeit ${index + 1} entfernen`}
              title="Pausenzeit entfernen"
              onClick={() => onChange(windows.filter((_, i) => i !== index))}
            >
              <X className="h-4 w-4" />
            </Button>
          ) : (
            <span />
          )}
        </div>
      ))}
      {windows.length < MAX_BREAK_WINDOWS && (
        <div>
          <Button type="button" size="sm" variant="outline" onClick={() => onChange([...windows, nextBreakWindow(windows)])}>
            Weitere Pausenzeit
          </Button>
        </div>
      )}
      {!breakWindowsValid(windows) && (
        <p className="text-xs text-red-600">Jede Pausenzeit braucht Beginn vor Ende, und sie dürfen sich nicht überschneiden.</p>
      )}
    </div>
  )
}
