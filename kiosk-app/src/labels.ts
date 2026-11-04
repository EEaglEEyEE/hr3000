import type { PunchType } from './api'

export const PUNCH_TYPE_LABELS: Record<PunchType, string> = {
  COME: 'Kommen',
  GO: 'Gehen',
  BREAK_START: 'Pause Start',
  BREAK_END: 'Pause Ende',
  ERRAND_START: 'Dienstgang Start',
  ERRAND_END: 'Dienstgang Ende',
}
