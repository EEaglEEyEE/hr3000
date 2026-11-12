/** Testdaten in der Form der API-Antworten (Typen aus der OpenAPI-Spec). */
import type { components } from '../api/schema'

type Schemas = components['schemas']
export type DashboardMe = Schemas['DashboardMe']
export type DashboardResponse = Schemas['DashboardResponse']

export function dashboardMe(overrides: Partial<DashboardMe> = {}): DashboardMe {
  return {
    employee_id: 5,
    first_name: 'Erika',
    balance_minutes: 90,
    balance_date: '2026-10-20',
    vacation_year: 2026,
    vacation_remaining_days: 12.5,
    vacation_expiring_days: 0,
    vacation_expiry_date: null,
    today_status: null,
    today_times: '',
    today_actual_minutes: null,
    week_target_minutes: 2400,
    week_actual_minutes: 960,
    pending_absences: 0,
    pending_corrections: 0,
    on_demand: false,
    portal_punching: false,
    break_buttons: true,
    errand_buttons: false,
    location_check: false,
    location_check_required: false,
    month_actual_minutes: null,
    monthly_cap_minutes: null,
    ...overrides,
  }
}

export function dashboard(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
  return {
    me: null,
    team: null,
    events: [],
    horizon_date: '2026-11-20',
    portal_punching_enabled: false,
    self_time_entry_enabled: false,
    absence_requests_enabled: true,
    team_calendar_for_employees: false,
    org_chart_for_employees: false,
    shift_planning_enabled: false,
    ...overrides,
  }
}

export function team(overrides: Partial<Schemas['DashboardTeam']> = {}): Schemas['DashboardTeam'] {
  return { present: [], on_break: [], on_errand: [], absent: [], visible_employees: 0, ...overrides }
}

export function openDay(employeeId: number, workDate: string): Schemas['OpenDayResponse'] {
  return {
    employee_id: employeeId,
    first_name: 'Max',
    last_name: 'Beispiel',
    location_id: 1,
    work_date: workDate,
    status: 'OPEN_MISSING_PUNCH',
    flags: [],
    times: '08:00–…',
  }
}

/** Routen, die die HR-Startseite zusätzlich lädt ("Zu erledigen"-Kacheln). */
export function hrTodoRoutes({
  openDays = [] as Schemas['OpenDayResponse'][],
  pendingAbsences = [] as unknown[],
  corrections = [] as unknown[],
  caps = [] as Schemas['MonthlyCapRow'][],
  limits = [] as Schemas['BalanceLimitRow'][],
} = {}): Record<string, unknown> {
  return {
    'GET /timesheet/open-days': openDays,
    'GET /absences/pending': pendingAbsences,
    'GET /punch-correction-requests': corrections,
    'GET /timesheet/monthly-caps': caps,
    'GET /timesheet/balance-limits': limits,
  }
}

/** Standard-Einstellungen eines neuen Mandanten (wie GET /settings sie liefert). */
export function settings(overrides: Partial<Schemas['SettingsResponse']> = {}): Schemas['SettingsResponse'] {
  return {
    require_pin_for_punch: false,
    default_bundesland: null,
    default_annual_vacation_days: 0,
    show_birthdays_in_calendar: false,
    shift_planning_enabled: false,
    balance_start_date: null,
    smtp_host: null,
    smtp_port: 587,
    smtp_user: null,
    smtp_from: null,
    smtp_security: 'STARTTLS',
    smtp_password_set: false,
    email_notifications_enabled: true,
    default_auto_break: true,
    default_show_birthday: true,
    default_day_minutes: null,
    prorate_part_time_vacation: true,
    prorate_partial_year_vacation: true,
    vacation_carry_over_auto: false,
    vacation_carry_over_max_days: null,
    vacation_carry_over_expiry: null,
    disabled_day_flags: [],
    report_days_without_punches: true,
    max_shift_span_hours: 16,
    core_time_start: null,
    core_time_end: null,
    core_time_days: null,
    datev_consultant_number: null,
    datev_client_number: null,
    punctuality_from: null,
    legal_break_minimum: true,
    break_precise_from: null,
    break_capped_from: null,
    late_tolerance_minutes: 5,
    flex_frame_start: null,
    flex_frame_end: null,
    kiosk_admin_pin_set: false,
    rfid_required: false,
    kiosk_rfid_enabled: true,
    kiosk_card_self_registration: true,
    kiosk_pin_self_setup: true,
    kiosk_show_balance: true,
    kiosk_show_vacation: true,
    kiosk_break_buttons: true,
    kiosk_errand_buttons: false,
    portal_punching_enabled: false,
    punch_location_check_enabled: false,
    punch_location_mode: 'RECORD',
    self_time_entry_enabled: false,
    self_time_entry_approval: true,
    self_time_entry_backdate_days: 7,
    project_times_enabled: false,
    project_required: false,
    whistleblowing_enabled: false,
    absence_requests_enabled: true,
    absence_four_eyes: false,
    absence_overlaps_for_employees: false,
    overtime_limit_max_hours: null,
    overtime_limit_min_hours: null,
    reminders_enabled: false,
    payroll_accounting_enabled: false,
    reduce_vacation_parental_leave: false,
    seniority_leave_rules: [],
    team_calendar_for_employees: false,
    org_chart_for_employees: false,
    custom_reports_enabled: false,
    two_factor_roles: [],
    kiosk_greeting: null,
    recruiting_enabled: false,
    recruiting_privacy_text: null,
    recruiting_privacy_url: null,
    recruiting_retention_months: 6,
    recruiting_talent_pool_months: 12,
    kiosk_sort: 'LAST_NAME',
    kiosk_theme: 'DARK',
    kiosk_screen_on_from: null,
    kiosk_screen_on_until: null,
    ...overrides,
  }
}

export function employee(overrides: Partial<Schemas['EmployeeResponse']> = {}): Schemas['EmployeeResponse'] {
  return {
    id: 5,
    location_id: 1,
    first_name: 'Erika',
    last_name: 'Muster',
    employee_number: '1001',
    active: true,
    login_email: null,
    two_factor_enabled: false,
    hr_role: null,
    hr_payroll_access: false,
    auto_break_enabled: true,
    has_pin: false,
    nfc_uid: null,
    hire_date: null,
    termination_date: null,
    birth_date: null,
    show_birthday_in_calendar: true,
    effective_supervisor_ids: [],
    supervisor_source: null,
    department_id: null,
    position: null,
    supervisor_id: null,
    employment_status: 'ACTIVE',
    cost_centers: [],
    anonymized_at: null,
    ...overrides,
  } as Schemas['EmployeeResponse']
}
