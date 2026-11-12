/** Anzeige-Helfer der Analysen (Monate, Zellen eigener Berichte). */
import { formatDate } from './format'

const MONTH_NAMES = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/** "2025-03" -> "Mär 2025" */
export function monthLabel(key: string): string {
  const [year, month] = key.split('-').map(Number)
  return `${MONTH_NAMES[month - 1]} ${year}`
}

/** Monat "YYYY-MM" um n Monate verschoben. */
export function shiftMonth(key: string, months: number): string {
  const [year, month] = key.split('-').map(Number)
  const index = year * 12 + (month - 1) + months
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`
}

/** Zelle eines eigenen Berichts: Datum TT.MM.JJJJ, Zahlen mit Komma, Ja/Nein, leer als „–“. */
export function formatCell(type: string, value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === '') return '–'
  if (typeof value === 'boolean') return value ? 'Ja' : 'Nein'
  if (typeof value === 'number') return value.toLocaleString('de-DE', { maximumFractionDigits: 2 })
  if (type === 'date') return formatDate(value)
  return value
}
