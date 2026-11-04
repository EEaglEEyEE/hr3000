import { useState } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'
import { getThemePreference, setThemePreference, type ThemePreference } from '../../lib/theme'
import { cn } from '../../lib/utils'

const OPTIONS: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Hell', icon: Sun },
  { value: 'dark', label: 'Dunkel', icon: Moon },
  { value: 'system', label: 'Wie System', icon: Monitor },
]

/** Hell / Dunkel / wie Betriebssystem – pro Browser gespeichert. */
export function ThemeToggle({ className }: { className?: string }) {
  const [preference, setPreference] = useState(getThemePreference)
  return (
    <div className={cn('flex gap-0.5 rounded-md bg-slate-100 p-0.5', className)} role="radiogroup" aria-label="Darstellung">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={preference === value}
          title={label}
          onClick={() => {
            setThemePreference(value)
            setPreference(value)
          }}
          className={cn(
            'flex flex-1 items-center justify-center rounded px-2 py-1 text-slate-500 hover:text-slate-900',
            preference === value && 'bg-white text-slate-900 shadow-sm',
          )}
        >
          <Icon className="h-4 w-4" />
        </button>
      ))}
    </div>
  )
}
