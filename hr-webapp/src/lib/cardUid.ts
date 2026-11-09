/** Zufällige Chip-UID für Mitarbeiter ohne Chip (16 Hex-Zeichen, wie eine lange Karten-UID). */
export function randomCardUid(): string {
  const bytes = new Uint8Array(8)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('').toUpperCase()
}
