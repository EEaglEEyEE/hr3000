/** Leitungen und Stellvertretungen einer Abteilung: Rollen und Rechte (wie im Backend,
 *  app/services/scope_service.py). */
export type LeaderRole = 'HEAD' | 'DEPUTY'
export type DeputyRights = 'STANDBY' | 'FULL' | 'ABSENCE'

export const ROLE_LABELS: Record<LeaderRole, string> = { HEAD: 'Leitung', DEPUTY: 'Stellvertretung' }

/** Auswahl im Dialog */
export const DEPUTY_RIGHTS_LABELS: Record<DeputyRights, string> = {
  STANDBY: 'Sieht immer, entscheidet bei Abwesenheit',
  FULL: 'Gleiche Rechte wie die Leitung',
  ABSENCE: 'Nur während Abwesenheit der Leitung',
}

/** Kurzform für Karten und Tabellen */
export const DEPUTY_RIGHTS_SHORT: Record<DeputyRights, string> = {
  STANDBY: 'bei Abwesenheit',
  FULL: 'gleiche Rechte',
  ABSENCE: 'nur bei Abwesenheit',
}

export const DEPUTY_RIGHTS_HELP: Record<DeputyRights, string> = {
  STANDBY: 'Sieht die Abteilung wie die Leitung. Entscheidet und wird benachrichtigt, wenn keine Leitung da ist.',
  FULL: 'Sieht und entscheidet immer und wird wie die Leitung benachrichtigt.',
  ABSENCE: 'Sieht und entscheidet nur, solange keine Leitung da ist.',
}
