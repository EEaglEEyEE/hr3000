/** Rechte der Oberfläche aus einer Quelle: Menü, Einstellungs-Bereiche und Seitenschutz lesen alle
 * hier. Die Stufen entsprechen den Abhängigkeiten im Backend, das dasselbe erzwingt:
 * - all     = get_current_hr_principal (auch Führungskraft, mit Team-Filter)
 * - hr      = get_current_full_hr_principal (Admin und HR)
 * - payroll = get_current_payroll_principal (Berechtigung „Vergütung & Lohn-Export“)
 * - admin   = get_current_admin_principal */
export type Access = 'all' | 'hr' | 'payroll' | 'admin'

export interface AccessFlags {
  isAdmin: boolean
  isFullHr: boolean
  canPayroll: boolean
  /** Eigene Rolle (Token-Claim perms): Stufe je Bereich; null/fehlend = keine eigene Rolle. */
  perms?: Perms | null
}

/** Bereiche eigener Rollen – wie app/services/role_permissions.Area im Backend. */
export const AREAS = [
  'EMPLOYEES',
  'DOCUMENTS',
  'PAYROLL',
  'TIME',
  'ABSENCES',
  'SHIFT_PLANNING',
  'PERIOD_CLOSURE',
  'REPORTS',
  'ORGANIZATION',
  'CHECKLISTS',
  'MASTER_DATA',
  'RECRUITING',
] as const
export type Area = (typeof AREAS)[number]
export type Level = 'NONE' | 'VIEW' | 'EDIT'
export type Perms = Partial<Record<Area, Level>>

const RANK: Record<Level, number> = { NONE: 0, VIEW: 1, EDIT: 2 }

/** Ohne eigene Rolle immer true – dann entscheidet allein die Rolle (Admin/HR/Führungskraft). */
export function hasArea(perms: Perms | null | undefined, area: Area, level: Level = 'VIEW'): boolean {
  if (!perms) return true
  return RANK[perms[area] ?? 'NONE'] >= RANK[level]
}

/** Mindestens einer der Bereiche (je mit Stufe, Standard „Ansehen“). */
export type AreaNeed = (Area | [Area, Level])[]

export function allowsAreas(need: AreaNeed | undefined, perms: Perms | null | undefined): boolean {
  if (!perms) return true
  // Deny by default: Seiten ohne Zuordnung sind für eigene Rollen nicht sichtbar.
  if (!need) return false
  return need.some((entry) => (Array.isArray(entry) ? hasArea(perms, entry[0], entry[1]) : hasArea(perms, entry)))
}

/** Nachschlagelisten (Mitarbeiter, Standorte …): irgendein Bereich, „Vergütung & Lohn“ erst ab Bearbeiten
 * – wie role_permissions.has_lookup_access im Backend. */
export const LOOKUP: AreaNeed = AREAS.map((area): Area | [Area, Level] => (area === 'PAYROLL' ? ['PAYROLL', 'EDIT'] : area))

export function allows(access: Access, flags: AccessFlags): boolean {
  switch (access) {
    case 'all':
      return true
    case 'hr':
      return flags.isFullHr
    case 'payroll':
      return flags.canPayroll
    case 'admin':
      return flags.isAdmin
  }
}

/** Bereiche je Seite für Konten mit eigener Rolle (zusätzlich zu PAGE_ACCESS). Seiten ohne Eintrag
 * sehen sie nicht. Das Backend prüft dasselbe je Endpoint (role_permissions.ROUTE_RULES). */
export const PAGE_AREAS: Record<string, AreaNeed> = {
  '/': LOOKUP,
  '/mitarbeiter': LOOKUP,
  '/mitarbeiter-import': [['EMPLOYEES', 'EDIT']],
  '/uebersicht': ['TIME'],
  '/team-kalender': ['ABSENCES', 'SHIFT_PLANNING'],
  '/organigramm': ['ORGANIZATION', 'EMPLOYEES'],
  '/zu-klaeren': ['TIME', 'ABSENCES', 'EMPLOYEES'],
  '/schichtplan-kalender': ['SHIFT_PLANNING'],
  '/monatsabschluss': ['PERIOD_CLOSURE'],
  '/auswertungen': ['REPORTS'],
  '/lohn-export': [['PAYROLL', 'EDIT']],
  '/lohnbuchhaltung': ['PAYROLL'],
  '/checklisten': ['CHECKLISTS'],
  '/einstellungen': ['MASTER_DATA', 'ORGANIZATION', 'SHIFT_PLANNING', ['PAYROLL', 'EDIT']],
}

/** Seiten, deren Sichtbarkeit das Backend je Konto meldet (Hinweise: benannte Beauftragte, Recruiting:
 * /recruiting/access mit Bereich „Recruiting“ oder Hiring Team) – hier ohne Bereichsprüfung. */
export const BACKEND_DECIDES: ReadonlySet<string> = new Set(['/hinweise', '/recruiting'])

/** Seite erlaubt? Rolle (PAGE_ACCESS) oder eingeschalteter Schalter (PAGE_FEATURE_ACCESS), dazu bei
 * eigener Rolle der Bereich (PAGE_AREAS). */
export function allowsPage(path: string, flags: AccessFlags, features?: Partial<Record<PageFeature, boolean>>): boolean {
  const feature = PAGE_FEATURE_ACCESS[path]
  const byRole =
    allows(PAGE_ACCESS[path] ?? 'all', flags) || (feature !== undefined && feature.some((key) => features?.[key] === true))
  return byRole && (BACKEND_DECIDES.has(path) || allowsAreas(PAGE_AREAS[path], flags.perms))
}

/** Rechte je Seite (Pfad wie im Router). Seiten ohne Eintrag sind für alle HR-Rollen offen. */
export const PAGE_ACCESS: Record<string, Access> = {
  '/': 'all',
  '/mitarbeiter': 'all',
  '/uebersicht': 'all',
  '/team-kalender': 'all',
  '/organigramm': 'all',
  '/zu-klaeren': 'all',
  '/mitarbeiter-import': 'hr',
  '/schichtplan-kalender': 'hr',
  '/monatsabschluss': 'hr',
  '/auswertungen': 'hr',
  '/lohn-export': 'hr',
  '/lohnbuchhaltung': 'payroll',
  '/checklisten': 'hr',
  // Recruiting: Admin/HR und Konten im Hiring Team (Sichtbarkeit prüft das Backend)
  '/recruiting': 'all',
  '/einstellungen': 'hr',
}

/** Schalter, mit denen eine Seite zusätzlich allen Verwaltungskonten (auch Führungskräften) offensteht
 * (einer genügt): „Analysen“ zeigt Führungskräften bei eingeschalteten eigenen Berichten den Reiter
 * „Eigene Berichte“, bei eingeschalteten Projektzeiten den Reiter „Projektzeiten“ – jeweils nur ihr
 * Bereich (Backend: get_current_hr_principal, Bereich über scope_service). */
export type PageFeature = 'custom_reports_enabled' | 'project_times_enabled'
export const PAGE_FEATURE_ACCESS: Record<string, PageFeature[]> = {
  '/auswertungen': ['custom_reports_enabled', 'project_times_enabled'],
}

/** Frühere Bezeichnung, gleichbedeutend mit allowsPage. */
export const pageAllowed = allowsPage
