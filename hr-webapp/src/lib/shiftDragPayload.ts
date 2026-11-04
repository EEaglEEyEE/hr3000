/** Kontrakt für natives HTML5-Drag&Drop im Schichtplan-Kalender (siehe
 * ShiftPlanCalendarPage.tsx) – zwischen Vorlagen-Palette und Kalenderzellen
 * über dataTransfer als JSON übertragen. */
export type ShiftDragPayload =
  | { kind: 'template'; templateId: number }
  | { kind: 'off' }
  | { kind: 'move'; employeeId: number; sourceDate: string; templateId: number | null; isWorkday: boolean }

const MIME_TYPE = 'application/json'

export function setShiftDragPayload(event: React.DragEvent, payload: ShiftDragPayload): void {
  event.dataTransfer.setData(MIME_TYPE, JSON.stringify(payload))
  event.dataTransfer.effectAllowed = 'copyMove'
}

export function readShiftDragPayload(event: React.DragEvent): ShiftDragPayload | null {
  const raw = event.dataTransfer.getData(MIME_TYPE)
  if (!raw) return null
  try {
    return JSON.parse(raw) as ShiftDragPayload
  } catch {
    return null
  }
}
