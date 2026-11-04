export function formatMinutesAsHours(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '–'
  const sign = minutes < 0 ? '-' : minutes > 0 ? '+' : ''
  const abs = Math.abs(minutes)
  const hours = Math.floor(abs / 60)
  const mins = abs % 60
  return `${sign}${hours}:${String(mins).padStart(2, '0')}`
}

export function formatClock(date: Date): string {
  return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
}

/** Tage mit deutschem Komma, halbe Tage z.B. "12,5". */
export function formatDays(days: number): string {
  return days.toLocaleString('de-DE', { maximumFractionDigits: 1 })
}
