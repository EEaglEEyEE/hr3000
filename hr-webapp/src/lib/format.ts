export function formatMinutesAsHours(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '–'
  const sign = minutes < 0 ? '-' : minutes > 0 ? '+' : ''
  const abs = Math.abs(minutes)
  const hours = Math.floor(abs / 60)
  const mins = abs % 60
  return `${sign}${hours}:${String(mins).padStart(2, '0')}`
}

/** Das Backend liefert timestamp_utc als naiven ISO-String ohne "Z"/Offset
 * (intern immer UTC, siehe docs/konzept.md). Ohne "Z" interpretiert der
 * Date-Konstruktor einen String mit Zeitanteil als Browser-Lokalzeit statt
 * UTC – das würde sonst je nach Browser-Zeitzone zu einer verschobenen Zeit
 * führen (kritisch bei Speichern nach dem Bearbeiten). */
function ensureUtcSuffix(iso: string): string {
  return /[Zz]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`
}

export function formatDateTime(iso: string): string {
  return new Date(ensureUtcSuffix(iso)).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

/** Datum als TT.MM.JJJJ. Ein reines Datum (JJJJ-MM-TT) bleibt unverändert; ein Zeitpunkt (mit „T“,
 * naiv in UTC wie vom Backend) wird als Datum in der Ortszeit des Browsers angezeigt – sonst ergäbe
 * `${iso}T00:00:00Z` „Invalid Date“. */
export function formatDate(iso: string): string {
  if (iso.includes('T')) return new Date(ensureUtcSuffix(iso)).toLocaleDateString('de-DE')
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('de-DE', { timeZone: 'UTC' })
}

/** ISO-UTC-Timestamp -> Wert für <input type="datetime-local"> in Browser-Lokalzeit. */
export function isoToLocalInputValue(iso: string): string {
  const date = new Date(ensureUtcSuffix(iso))
  const offsetMs = date.getTimezoneOffset() * 60000
  const local = new Date(date.getTime() - offsetMs)
  return local.toISOString().slice(0, 16)
}

/** Wert aus <input type="datetime-local"> (Browser-Lokalzeit) -> ISO-UTC-Timestamp. */
export function localInputValueToIso(value: string): string {
  return new Date(value).toISOString()
}

export function todayIsoDate(): string {
  const now = new Date()
  const offsetMs = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10)
}

export function daysAgoIsoDate(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() - days)
  const offsetMs = date.getTimezoneOffset() * 60000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 10)
}

export function daysFromNowIsoDate(days: number): string {
  return daysAgoIsoDate(-days)
}

/** Reine Kalenderdatum-Arithmetik (kein Zeitanteil) – über Date.UTC statt
 * Browser-Lokalzeit, damit DST-Umstellungen das Datum nie um einen Tag
 * verschieben (siehe mondayOfWeek/addDaysIsoDate unten). */
export function addDaysIsoDate(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function mondayOfWeek(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00Z`)
  const weekday = date.getUTCDay()
  const diffToMonday = weekday === 0 ? -6 : 1 - weekday
  return addDaysIsoDate(isoDate, diffToMonday)
}

export function weekdayShortLabel(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString('de-DE', { weekday: 'short', timeZone: 'UTC' })
}

export function currentYearMonth(): string {
  return todayIsoDate().slice(0, 7)
}

/** Vormonat als "YYYY-MM" – Standard für Abrechnungen (der laufende Monat ist noch nicht fertig). */
export function previousYearMonth(): string {
  const [year, month] = currentYearMonth().split('-').map(Number)
  return month === 1 ? `${year - 1}-12` : `${year}-${String(month - 1).padStart(2, '0')}`
}

/** "YYYY-MM" (Wert von <input type="month">) -> erster/letzter Kalendertag
 * dieses Monats, für Zeitraum-Filter wie den Lohn-Export. */
export function monthRange(yearMonth: string): { from: string; to: string } {
  const [year, month] = yearMonth.split('-').map(Number)
  const from = `${yearMonth}-01`
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate()
  const to = `${yearMonth}-${String(lastDay).padStart(2, '0')}`
  return { from, to }
}

/** Tage mit deutschem Komma, halbe Tage z.B. "12,5". */
export function formatDays(days: number): string {
  return days.toLocaleString('de-DE', { maximumFractionDigits: 1 })
}

/** Dauer ohne Vorzeichen, z.B. 90 -> "1:30". */
export function formatHoursMinutes(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`
}
