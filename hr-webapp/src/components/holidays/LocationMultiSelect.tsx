import { cn } from '../../lib/utils'

interface LocationOption {
  id: number
  name: string
}

/** Mehrfachauswahl von Standorten. Leere Auswahl bedeutet "Alle Standorte" –
 * so ist ein Feiertag ohne Zuordnung für jeden Standort gültig. */
export function LocationMultiSelect({
  locations,
  value,
  onChange,
  className,
}: {
  locations: LocationOption[]
  value: number[]
  onChange: (value: number[]) => void
  className?: string
}) {
  const all = value.length === 0

  function toggle(id: number) {
    onChange(value.includes(id) ? value.filter((entry) => entry !== id) : [...value, id])
  }

  return (
    <div className={cn('flex flex-col gap-1.5 rounded-md border border-slate-200 p-2', className)}>
      <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-slate-300"
          checked={all}
          onChange={() => onChange([])}
        />
        Alle Standorte
      </label>
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-100 pt-1.5">
        {locations.map((location) => (
          <label key={location.id} className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={value.includes(location.id)}
              onChange={() => toggle(location.id)}
            />
            {location.name}
          </label>
        ))}
        {locations.length === 0 && <span className="text-sm text-slate-400">Keine Standorte angelegt.</span>}
      </div>
      <p className="text-xs text-slate-500">Ohne Auswahl gilt der Feiertag für alle Standorte.</p>
    </div>
  )
}
