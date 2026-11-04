import { useEffect, useState } from 'react'

/** Uhrzeit "HH:MM" -> Minuten seit Mitternacht (null, wenn unlesbar). */
function toMinutes(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(value)
  if (!match) return null
  const hours = Number(match[1])
  const minutes = Number(match[2])
  return hours < 24 && minutes < 60 ? hours * 60 + minutes : null
}

/** Minuten seit Mitternacht in der Zeitzone des Standorts; bei ungültiger Zeitzone die Geräteuhr. */
function localMinutes(now: Date, timeZone: string): number {
  try {
    const parts = new Intl.DateTimeFormat('de-DE', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(now)
    const hour = Number(parts.find((part) => part.type === 'hour')?.value)
    const minute = Number(parts.find((part) => part.type === 'minute')?.value)
    if (Number.isFinite(hour) && Number.isFinite(minute)) return hour * 60 + minute
  } catch {
    // ungültige Zeitzone – unten auf die Geräteuhr zurückfallen
  }
  return now.getHours() * 60 + now.getMinutes()
}

/** Liegt `now` im Bildschirm-Zeitfenster [from, until)? `from > until` = über Mitternacht (z.B.
 * 22:00–06:00). Ohne Fenster (null) oder bei unlesbaren Werten: immer an – lieber zu lange hell
 * als ein dunkles Tablet. Wochentage gibt es (noch) nicht. */
export function isWithinScreenHours(
  now: Date,
  from: string | null | undefined,
  until: string | null | undefined,
  timeZone: string,
): boolean {
  if (!from || !until) return true
  const start = toMinutes(from)
  const end = toMinutes(until)
  if (start === null || end === null || start === end) return true
  const current = localMinutes(now, timeZone)
  return start < end ? current >= start && current < end : current >= start || current < end
}

/** Prüft das Fenster minütlich und bei jeder neuen Kiosk-Konfiguration. */
export function useScreenHours(
  from: string | null | undefined,
  until: string | null | undefined,
  timeZone: string | null | undefined,
): boolean {
  const zone = timeZone || 'Europe/Berlin'
  const [within, setWithin] = useState(() => isWithinScreenHours(new Date(), from, until, zone))
  useEffect(() => {
    const check = () => setWithin(isWithinScreenHours(new Date(), from, until, zone))
    check()
    const interval = setInterval(check, 60_000)
    return () => clearInterval(interval)
  }, [from, until, zone])
  return within
}
