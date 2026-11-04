import { useState } from 'react'
import type { Employee } from '../api'

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', '⌫']
const MAX_LENGTH = 8

export function PinPad({
  employee,
  isSubmitting,
  error,
  onSubmit,
  onCancel,
  title = 'Bitte PIN eingeben',
  minLength = 1,
}: {
  employee: Employee
  isSubmitting: boolean
  error: string | null
  onSubmit: (pin: string) => void
  onCancel: () => void
  title?: string
  /** Mindestlänge, ab der „Bestätigen“ möglich ist (z.B. 4 beim Festlegen eines neuen PINs) */
  minLength?: number
}) {
  const [pin, setPin] = useState('')

  function handleKey(key: string) {
    if (isSubmitting) return
    if (key === '⌫') {
      setPin((prev) => prev.slice(0, -1))
    } else if (key && pin.length < MAX_LENGTH) {
      setPin((prev) => prev + key)
    }
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 bg-slate-950 p-6 text-white">
      <h1 className="text-2xl font-semibold">
        {employee.first_name} {employee.last_name}
      </h1>
      <p className="text-slate-400">{title}</p>
      <div className="flex gap-3">
        {Array.from({ length: Math.max(pin.length, 4) }, (_, index) => (
          <span
            key={index}
            className={`h-4 w-4 rounded-full border-2 border-slate-500 ${index < pin.length ? 'bg-white' : ''}`}
          />
        ))}
      </div>

      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((key, index) => (
          <button
            key={`${key}-${index}`}
            type="button"
            disabled={!key || isSubmitting}
            onClick={() => handleKey(key)}
            className="h-16 w-20 rounded-xl bg-slate-800 text-2xl font-medium disabled:opacity-0 hover:bg-slate-700"
          >
            {key}
          </button>
        ))}
      </div>

      {error && <p className="text-red-400">{error}</p>}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="rounded-lg border border-slate-700 px-6 py-3 text-lg text-slate-300"
        >
          Abbrechen
        </button>
        <button
          type="button"
          onClick={() => onSubmit(pin)}
          disabled={isSubmitting || pin.length < minLength}
          className="rounded-lg bg-emerald-500 px-6 py-3 text-lg font-medium text-slate-950 disabled:opacity-50"
        >
          {isSubmitting ? 'Prüfe…' : 'Bestätigen'}
        </button>
      </div>
    </div>
  )
}
