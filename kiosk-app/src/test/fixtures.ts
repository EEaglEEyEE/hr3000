import type { Employee } from '../api'
import type { QueuedPunch } from '../offlineQueue'

export function employee(overrides: Partial<Employee> = {}): Employee {
  return {
    id: 1,
    first_name: 'Erika',
    last_name: 'Muster',
    employee_number: 'T1',
    has_pin: false,
    nfc_uid: null,
    today_status: 'OPEN_MISSING_PUNCH',
    ...overrides,
  }
}

export function queued(key: string, overrides: Partial<QueuedPunch> = {}): QueuedPunch {
  return {
    idempotency_key: key,
    employee_id: 1,
    employee_name: 'Erika Muster',
    punch_type: 'COME',
    timestamp_utc: '2026-10-21T06:00:00.000Z',
    ...overrides,
  }
}
