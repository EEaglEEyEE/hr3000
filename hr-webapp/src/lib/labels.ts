import type { components } from '../api/schema'
import type { BadgeProps } from '../components/ui/badge'

type PunchType = components['schemas']['PunchType']
type PunchSource = components['schemas']['PunchSource']
type AbsenceType = components['schemas']['AbsenceType']
type SummaryStatus = components['schemas']['SummaryStatus']
type Bundesland = components['schemas']['Bundesland']
type AuditAction = components['schemas']['AuditAction']

export const PUNCH_TYPE_LABELS: Record<PunchType, string> = {
  COME: 'Kommen',
  GO: 'Gehen',
  BREAK_START: 'Pause Start',
  BREAK_END: 'Pause Ende',
  ERRAND_START: 'Dienstgang Start',
  ERRAND_END: 'Dienstgang Ende',
}

export const PUNCH_SOURCE_LABELS: Record<PunchSource, string> = {
  KIOSK: 'Tablet',
  MANUAL_HR: 'HR manuell',
  AUTO_BREAK: 'Automatisch (Pause)',
  PORTAL: 'Web-Login',
}

export const PUNCH_SOURCE_VARIANT: Record<PunchSource, BadgeProps['variant']> = {
  KIOSK: 'default',
  MANUAL_HR: 'warning',
  AUTO_BREAK: 'info',
  PORTAL: 'violet',
}

export const ABSENCE_TYPE_LABELS: Record<AbsenceType, string> = {
  VACATION: 'Urlaub',
  SICK: 'Krankheit',
  SPECIAL_LEAVE: 'Sonderurlaub',
  UNPAID: 'Unbezahlt',
  TIME_OFF_IN_LIEU: 'Freizeitausgleich',
  WORK_TIME: 'Arbeitszeit',
  PUBLIC_HOLIDAY: 'Feiertag',
  CHILD_SICK: 'Kind krank',
  PARENTAL_LEAVE: 'Mutterschutz/Elternzeit',
  SHORT_TIME_WORK: 'Kurzarbeit',
  UNEXCUSED: 'Unentschuldigt',
  CARE_LEAVE: 'Pflege von Angehörigen',
}

/** Wie eine Abwesenheitsart zählt (Kategorie) – Erklärung für die Einstellungen. */
export const ABSENCE_CATEGORY_HINTS: Record<AbsenceType, string> = {
  VACATION: 'Urlaub: Soll wird gutgeschrieben, zieht Urlaubstage ab',
  SICK: 'Krankheit: Soll wird gutgeschrieben',
  SPECIAL_LEAVE: 'Bezahlte Freistellung: Soll wird gutgeschrieben',
  UNPAID: 'Unbezahlt: Soll entfällt',
  TIME_OFF_IN_LIEU: 'Freizeitausgleich: Saldo sinkt um das Tagessoll',
  WORK_TIME: 'Arbeitszeit (z. B. Homeoffice, zusätzliche Stunden): zählt als gearbeitet, kein Abwesenheitstag',
  PUBLIC_HOLIDAY: 'Feiertag (z. B. Feiertag GfB): Soll wird gutgeschrieben, zählt als Feiertag',
  CHILD_SICK: 'Kind krank: Soll wird gutgeschrieben, wird getrennt von eigener Krankheit gezählt',
  PARENTAL_LEAVE: 'Mutterschutz/Elternzeit: Soll entfällt, eigene Spalte im Lohn-Export',
  SHORT_TIME_WORK: 'Kurzarbeit: Soll entfällt, eigene Spalte im Lohn-Export',
  UNEXCUSED: 'Unentschuldigtes Fehlen: Soll entfällt, eigene Spalte im Lohn-Export',
  CARE_LEAVE: 'Pflege von Angehörigen: Soll entfällt, eigene Spalte im Lohn-Export',
}

export const DAY_STATUS_LABELS: Record<SummaryStatus, string> = {
  COMPLETE: 'Vollständig',
  OPEN_MISSING_PUNCH: 'Zu klären',
  ABSENCE: 'Abwesend',
  PRESENT: 'Anwesend',
  ON_BREAK: 'Pause',
  ON_ERRAND: 'Dienstgang',
  ERROR: 'Fehlerhaft',
  HOLIDAY: 'Feiertag',
  PLANNED_OFF: 'Frei laut Plan',
}

export const AUDIT_ACTION_LABELS: Record<AuditAction, string> = {
  PUNCH_CORRECTED: 'Stempelung korrigiert',
  PUNCH_DELETED: 'Stempelung gelöscht',
  EMPLOYEE_HR_ROLE_CHANGED: 'HR-Rolle geändert',
  ABSENCE_DECIDED: 'Urlaubsantrag entschieden',
  EMPLOYEE_CREATED: 'Mitarbeiter angelegt',
  SETTINGS_CHANGED: 'Einstellungen geändert',
  HR_USER_CREATED: 'HR-Nutzer angelegt',
  HR_USER_DELETED: 'HR-Nutzer gelöscht',
  TEAM_CREATED: 'Team angelegt',
  TEAM_UPDATED: 'Team geändert',
  TEAM_DELETED: 'Team gelöscht',
  TENANT_ADMIN_EMAIL_CHANGED: 'Mandanten-Admin-E-Mail geändert',
  EMPLOYEES_BULK_IMPORTED: 'Mitarbeiter per CSV importiert',
  EMPLOYEE_DATA_EXPORTED: 'Datenexport (DSGVO Art. 15) erstellt',
  EMPLOYEE_ANONYMIZED: 'Mitarbeiter anonymisiert (DSGVO)',
  EMPLOYEE_WORK_TIME_MODEL_SET: 'Arbeitszeitmodell geändert',
  EMPLOYEE_PASSWORD_RESET: 'Passwort zurückgesetzt',
  CONTRACT_CHANGED: 'Vertragsdaten geändert',
  COMPENSATION_CHANGED: 'Vergütung geändert',
  COMPENSATION_VIEWED: 'Vergütung eingesehen',
  DOCUMENT_UPLOADED: 'Dokument hochgeladen',
  DOCUMENT_UPDATED: 'Dokument geändert',
  DOCUMENT_DELETED: 'Dokument gelöscht',
  DOCUMENT_ACCESSED: 'Dokument abgerufen',
  PERIOD_SUBMITTED: 'Monatsnachweis zur Bestätigung vorgelegt',
  PERIOD_CONFIRMED: 'Monatsnachweis bestätigt (abgeschlossen)',
  PERIOD_DISPUTED: 'Monatsnachweis beanstandet',
  PERIOD_CLOSED: 'Monat abgeschlossen',
  PERIOD_REOPENED: 'Monat wieder geöffnet',
  CHECKLIST_STARTED: 'On-/Offboarding zugewiesen',
  SURCHARGE_RULES_CHANGED: 'Zuschlagsregeln geändert',
  PUNCH_CORRECTION_DECIDED: 'Korrekturantrag entschieden',
  EMPLOYEE_CARD_REGISTERED: 'Chip am Tablet registriert',
  EMPLOYEE_PIN_SET_AT_KIOSK: 'PIN am Tablet festgelegt',
  BALANCE_ADJUSTED: 'Überstundenkonto gebucht',
  LOGIN: 'Anmeldung',
  LEAVE_ADJUSTED: 'Urlaubskonto korrigiert',
  DEVICE_LOGIN_REJECTED: 'Tablet-Anmeldung eines anderen Geräts abgewiesen',
  TWO_FACTOR_CHANGED: 'Zwei-Faktor-Anmeldung geändert',
  DEPARTMENT_CHANGED: 'Abteilung geändert',
  PERSONAL_DATA_CHANGED: 'Persönliche Daten geändert',
  COST_CENTERS_CHANGED: 'Kostenstellen geändert',
  ATTRIBUTE_CHANGED: 'Feld der Personalakte geändert',
  DEVICE_ENROLLMENT: 'Tablet-Registrierung per MDM',
}

export const AUDIT_ENTITY_TYPE_LABELS: Record<string, string> = {
  punch: 'Stempelung',
  employee: 'Mitarbeiter',
  absence: 'Abwesenheit',
  app_settings: 'Einstellungen',
  hr_user: 'HR-Konto',
  team: 'Team',
  surcharge_rule: 'Zuschlagsregel',
}

export const BUNDESLAND_LABELS: Record<Bundesland, string> = {
  BW: 'Baden-Württemberg',
  BY: 'Bayern',
  BE: 'Berlin',
  BB: 'Brandenburg',
  HB: 'Bremen',
  HH: 'Hamburg',
  HE: 'Hessen',
  MV: 'Mecklenburg-Vorpommern',
  NI: 'Niedersachsen',
  NW: 'Nordrhein-Westfalen',
  RP: 'Rheinland-Pfalz',
  SL: 'Saarland',
  SN: 'Sachsen',
  ST: 'Sachsen-Anhalt',
  SH: 'Schleswig-Holstein',
  TH: 'Thüringen',
}

export const CONTRACT_TYPE_LABELS: Record<components['schemas']['ContractResponse']['contract_type'], string> = {
  PERMANENT: 'Unbefristet',
  FIXED_TERM: 'Befristet',
  APPRENTICESHIP: 'Ausbildung',
  MINI_JOB: 'Minijob',
  WORKING_STUDENT: 'Werkstudent',
  INTERNSHIP: 'Praktikum',
  FREELANCE: 'Freie Mitarbeit',
}

export const PAY_TYPE_LABELS: Record<components['schemas']['CompensationResponse']['pay_type'], string> = {
  HOURLY: 'Stundenlohn',
  MONTHLY: 'Monatsgehalt',
}

export const DOCUMENT_CATEGORY_LABELS: Record<components['schemas']['DocumentResponse']['category'], string> = {
  CONTRACT: 'Vertrag',
  CERTIFICATE: 'Zeugnis / Zertifikat',
  SICK_NOTE: 'Krankmeldung (AU)',
  QUALIFICATION: 'Qualifikation',
  WARNING: 'Abmahnung',
  PAYROLL: 'Lohn / Gehalt',
  TIME_REPORT: 'Monatsnachweis',
  OTHER: 'Sonstiges',
}

export const PERIOD_STATUS_LABELS: Record<components['schemas']['PeriodClosureResponse']['status'], string> = {
  SUBMITTED: 'Zur Bestätigung vorgelegt',
  DISPUTED: 'Widerspruch',
  CLOSED: 'Abgeschlossen',
}

export const PERIOD_STATUS_VARIANT: Record<
  components['schemas']['PeriodClosureResponse']['status'],
  BadgeProps['variant']
> = {
  SUBMITTED: 'warning',
  DISPUTED: 'danger',
  CLOSED: 'success',
}

export const SURCHARGE_KIND_LABELS: Record<components['schemas']['SurchargeRuleResponse']['kind'], string> = {
  NIGHT: 'Nachtarbeit (Zeitfenster)',
  SUNDAY: 'Sonntag',
  HOLIDAY: 'Feiertag',
  OVERTIME: 'Mehrarbeit (über Tages-Soll)',
  CUSTOM: 'Freies Zeitfenster',
}

export const CHECKLIST_KIND_LABELS: Record<components['schemas']['ChecklistResponse']['kind'], string> = {
  ONBOARDING: 'Onboarding',
  OFFBOARDING: 'Offboarding',
}

export const CHECKLIST_ROLE_LABELS: Record<components['schemas']['ChecklistRole'], string> = {
  HR: 'HR',
  IT: 'IT',
  SUPERVISOR: 'Führungskraft',
  EMPLOYEE: 'Mitarbeiter/in',
  OTHER: 'Sonstige',
}

/** Gründe, warum ein Tag trotz Stempelung unter "Zu klären" erscheint (siehe Backend DayFlag). */
export const DAY_FLAG_LABELS: Record<string, string> = {
  UNPLANNED_WORK: 'Außerplanmäßig gestempelt (laut Plan frei)',
  WORK_DURING_ABSENCE: 'Gestempelt trotz Abwesenheit',
  HOLIDAY_WORK: 'Arbeit an einem Feiertag',
  OUTSIDE_EMPLOYMENT: 'Außerhalb des Beschäftigungszeitraums',
  OVER_MAX_DAILY: 'Mehr als 10 Std. gearbeitet (§3 ArbZG)',
  LATE_ARRIVAL: 'Zu spät gekommen (nach Schicht-/Kernzeitbeginn)',
  EARLY_LEAVE: 'Zu früh gegangen (vor Schicht-/Kernzeitende)',
  OUTSIDE_FLEX_FRAME: 'Außerhalb der Gleitzeit-Rahmenzeit gestempelt',
}

/** Status wie in der Personalakte (aus Eintritt/Austritt, Aktiv und Elternzeit/Pflegezeit). */
export const EMPLOYMENT_STATUS_LABELS: Record<string, string> = {
  ONBOARDING: 'Onboarding',
  ACTIVE: 'Aktiv',
  LEAVE: 'Auszeit',
  INACTIVE: 'Inaktiv',
}

/** Aktion einer On-/Offboarding-Aufgabe. */
export const CHECKLIST_ACTION_LABELS: Record<string, string> = {
  TASK: 'Abhaken',
  UPLOAD_DOCUMENT: 'Person lädt Dokument hoch',
  FILL_DATA: 'Person trägt Daten ein',
  SEND_EMAIL: 'E-Mail beim Start senden',
}
