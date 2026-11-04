export type PunchType = 'COME' | 'GO' | 'BREAK_START' | 'BREAK_END' | 'ERRAND_START' | 'ERRAND_END'
export type SummaryStatus =
  | 'COMPLETE'
  | 'OPEN_MISSING_PUNCH'
  | 'ABSENCE'
  | 'PRESENT'
  | 'ON_BREAK'
  | 'ON_ERRAND'
  | 'ERROR'

/** Einstellungen → Kiosk (Anzeige/Verhalten), beim Login und regelmäßig über /device/config. */
export interface KioskConfig {
  require_pin: boolean
  rfid_required?: boolean
  /** Chip-Funktion am Tablet (Terminalleiste, Mitarbeiter per Chip öffnen); Standard: an */
  rfid_enabled?: boolean
  /** Mitarbeiter dürfen ihren Chip selbst registrieren (mit PIN) */
  card_self_registration?: boolean
  /** Ohne PIN: beim ersten Stempeln am Tablet selbst festlegen */
  pin_self_setup?: boolean
  show_balance?: boolean
  show_vacation?: boolean
  break_buttons?: boolean
  /** Dienstgang-Buttons anzeigen (Standard: an) */
  errand_buttons?: boolean
  greeting?: string | null
  sort?: 'LAST_NAME' | 'FIRST_NAME'
  /** Darstellung am Tablet (Standard: dunkel) */
  theme?: 'DARK' | 'LIGHT'
  /** Bildschirm nur in diesem Fenster wach halten ("HH:MM", Gerät vor Mandant); null = immer an */
  screen_on_from?: string | null
  screen_on_until?: string | null
  /** IANA-Zeitzone des Standorts (maßgeblich für die Bildschirmzeiten) */
  timezone?: string
}

export interface DeviceLoginResponse extends KioskConfig {
  access_token: string
  token_type: string
  location_id: number
  device_name: string
}

export interface Employee {
  id: number
  first_name: string
  last_name: string
  employee_number: string
  has_pin: boolean
  nfc_uid: string | null
  today_status: SummaryStatus
}

export interface OvertimeBalance {
  employee_id: number
  balance_date: string | null
  running_balance_minutes: number
}

export interface LeaveEntitlement {
  employee_id: number
  year: number
  entitled_days: number
  carried_over_days: number
  used_days: number
  remaining_days: number
}

export class ApiError extends Error {
  status: number
  code: string | undefined

  constructor(status: number, code: string | undefined, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** Unterscheidet "Server hat abgelehnt" (ApiError) von "Server nicht erreichbar"
 * (fetch selbst wirft, z.B. kein WLAN) – nur letzteres darf in die Offline-Queue. */
export class NetworkError extends Error {
  constructor() {
    super('Keine Verbindung zum Server.')
    this.name = 'NetworkError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    throw new NetworkError()
  }
  if (!response.ok) {
    let detail = 'Unbekannter Fehler.'
    let code: string | undefined
    try {
      const body = (await response.json()) as { detail?: string; code?: string }
      detail = body.detail ?? detail
      code = body.code
    } catch {
      // keine JSON-Fehlerantwort
    }
    throw new ApiError(response.status, code, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Prüft die Kiosk-Admin-PIN des Mandanten (Voraussetzung zum Zurücksetzen des Geräts). */
export function verifyAdminPin(pin: string, accessToken: string): Promise<void> {
  return request<void>('/devices/verify-admin-pin', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ pin }),
  })
}

/** Ersten eigenen PIN am Tablet festlegen (nur solange noch keiner hinterlegt ist). */
export function setupPin(accessToken: string, payload: { employee_id: number; pin: string }): Promise<void> {
  return request('/device/setup-pin', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(payload),
  })
}

/** Eigenen RFID-Chip am Tablet registrieren (Bestätigung mit dem PIN des Mitarbeiters). */
export function registerCard(accessToken: string, payload: { employee_id: number; pin: string; nfc_uid: string }): Promise<void> {
  return request('/device/register-card', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(payload),
  })
}

/** Kurzen Kopplungscode (HR-Webapp → Tablets → QR-Code) gegen das Geräte-Token tauschen. */
export function pairDevice(code: string): Promise<{ device_token: string }> {
  return request('/auth/device/pair', { method: 'POST', body: JSON.stringify({ code }) })
}

export function deviceLogin(deviceToken: string): Promise<DeviceLoginResponse> {
  return request('/auth/device/login', {
    method: 'POST',
    body: JSON.stringify({ device_token: deviceToken }),
  })
}

export function getKioskConfig(accessToken: string): Promise<KioskConfig> {
  return request('/device/config', { headers: { Authorization: `Bearer ${accessToken}` } })
}

export function listLocationEmployees(locationId: number, accessToken: string): Promise<Employee[]> {
  return request(`/locations/${locationId}/employees`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

export function createPunch(
  accessToken: string,
  payload: {
    employee_id: number
    punch_type: PunchType
    timestamp_utc: string
    idempotency_key: string
    pin?: string
    nfc_uid?: string
  },
): Promise<unknown> {
  return request('/punches', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(payload),
  })
}

export function getOvertimeBalance(employeeId: number, accessToken: string): Promise<OvertimeBalance> {
  return request(`/employees/${employeeId}/overtime-balance`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

export function getLeaveEntitlement(
  employeeId: number,
  accessToken: string,
  year: number = new Date().getFullYear(),
): Promise<LeaveEntitlement> {
  return request(`/employees/${employeeId}/leave-entitlement?year=${year}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

/** crypto.randomUUID() setzt einen sicheren Kontext (HTTPS/localhost) voraus –
 * ein Tablet im WLAN greift oft per HTTP+LAN-IP zu, daher mit Fallback. */
export function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}
