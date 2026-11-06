/** Rechte der Oberfläche aus einer Quelle: Menü, Einstellungs-Bereiche und Seitenschutz lesen alle
 * hier. Die Stufen entsprechen den Abhängigkeiten im Backend, das dasselbe erzwingt:
 * - all     = get_current_hr_principal (auch Teamleiter/in, mit Team-Filter)
 * - hr      = get_current_full_hr_principal (Admin und HR)
 * - payroll = get_current_payroll_principal (Berechtigung „Vergütung & Lohn-Export“)
 * - admin   = get_current_admin_principal */
export type Access = 'all' | 'hr' | 'payroll' | 'admin'

export interface AccessFlags {
  isAdmin: boolean
  isFullHr: boolean
  canPayroll: boolean
}

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

/** Rechte je Seite (Pfad wie im Router). Seiten ohne Eintrag sind für alle HR-Rollen offen. */
export const PAGE_ACCESS: Record<string, Access> = {
  '/': 'all',
  '/mitarbeiter': 'all',
  '/uebersicht': 'all',
  '/team-kalender': 'all',
  '/zu-klaeren': 'all',
  '/mitarbeiter-import': 'hr',
  '/schichtplan-kalender': 'hr',
  '/monatsabschluss': 'hr',
  '/auswertungen': 'hr',
  '/lohn-export': 'hr',
  '/checklisten': 'hr',
  '/einstellungen': 'hr',
}
