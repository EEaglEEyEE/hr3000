import type { components } from '../api/schema'

export type PunchPosition = components['schemas']['PunchPosition']

/** Obergrenze des Backends für die Genauigkeitsangabe (punch_location_service.MAX_ACCURACY_M). */
export const MAX_ACCURACY_M = 100_000

/**
 * Fragt die Position des Browsers genau einmal ab (nur im Moment des Stempelns bzw. auf Knopfdruck).
 * Nichts wird zwischengespeichert. Ergebnis `null`, wenn der Browser keine Standortfunktion hat, die
 * Freigabe verweigert wird, die Abfrage zu lange dauert oder die Angabe unbrauchbar ungenau ist – der
 * Server entscheidet dann je nach Modus („Standort unbekannt“ bzw. Ablehnung mit Meldung).
 */
export function currentPosition(timeoutMs = 10_000): Promise<PunchPosition | null> {
  if (typeof navigator === 'undefined' || !navigator.geolocation) return Promise.resolve(null)
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (result) => {
        const { latitude, longitude, accuracy } = result.coords
        if (![latitude, longitude, accuracy].every(Number.isFinite) || accuracy < 0 || accuracy > MAX_ACCURACY_M) {
          resolve(null)
          return
        }
        resolve({ latitude, longitude, accuracy_m: accuracy })
      },
      () => resolve(null),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 0 },
    )
  })
}

/** Zahl aus einem Eingabefeld (Komma oder Punkt); leer = null, ungültig = NaN. */
function parseNumber(value: string): number | null {
  const trimmed = value.trim().replace(',', '.')
  if (trimmed === '') return null
  return /^-?\d+(\.\d+)?$/.test(trimmed) ? Number(trimmed) : Number.NaN
}

export type Geofence = { geo_latitude: number; geo_longitude: number; geo_radius_m: number }

/** Prüft die drei Kreis-Felder: alle leer (= kein Kreis), alle gültig oder eine Fehlermeldung. */
export function parseGeofence(latitude: string, longitude: string, radius: string): Geofence | null | string {
  const lat = parseNumber(latitude)
  const lon = parseNumber(longitude)
  const rad = parseNumber(radius)
  if (lat === null && lon === null && rad === null) return null
  if (lat === null || lon === null || rad === null) return 'Kreis: bitte Breite, Länge und Radius angeben.'
  if (Number.isNaN(lat) || lat < -90 || lat > 90) return 'Breite: bitte eine Zahl zwischen -90 und 90 angeben.'
  if (Number.isNaN(lon) || lon < -180 || lon > 180) return 'Länge: bitte eine Zahl zwischen -180 und 180 angeben.'
  if (Number.isNaN(rad) || !Number.isInteger(rad) || rad < 50 || rad > 5000) return 'Radius: bitte ganze Meter zwischen 50 und 5000 angeben.'
  return { geo_latitude: lat, geo_longitude: lon, geo_radius_m: rad }
}
