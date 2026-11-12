import { describe, expect, it } from 'vitest'
import { AREAS, BACKEND_DECIDES, LOOKUP, PAGE_ACCESS, PAGE_AREAS, allowsAreas, allowsPage, hasArea, type Perms } from './access'

const HR = { isAdmin: false, isFullHr: true, canPayroll: false }
const OFFICE: Perms = { PAYROLL: 'VIEW' }

describe('hasArea', () => {
  it('ist ohne eigene Rolle immer erlaubt', () => {
    expect(hasArea(null, 'PAYROLL', 'EDIT')).toBe(true)
    expect(hasArea(undefined, 'TIME')).toBe(true)
  })
  it('vergleicht Stufen', () => {
    expect(hasArea({ TIME: 'VIEW' }, 'TIME')).toBe(true)
    expect(hasArea({ TIME: 'VIEW' }, 'TIME', 'EDIT')).toBe(false)
    expect(hasArea({ TIME: 'EDIT' }, 'TIME', 'VIEW')).toBe(true)
    expect(hasArea({ TIME: 'NONE' }, 'TIME')).toBe(false)
    expect(hasArea({}, 'TIME')).toBe(false)
  })
})

describe('allowsAreas', () => {
  it('ohne eigene Rolle: alles', () => {
    expect(allowsAreas(undefined, null)).toBe(true)
  })
  it('mit eigener Rolle: ohne Zuordnung verboten (deny by default)', () => {
    expect(allowsAreas(undefined, { TIME: 'EDIT' })).toBe(false)
  })
  it('einer der Bereiche genügt, je mit Stufe', () => {
    expect(allowsAreas(['TIME', 'ABSENCES'], { ABSENCES: 'VIEW' })).toBe(true)
    expect(allowsAreas([['PAYROLL', 'EDIT']], OFFICE)).toBe(false)
    expect(allowsAreas([['PAYROLL', 'EDIT']], { PAYROLL: 'EDIT' })).toBe(true)
  })
  it('Nachschlagelisten: Vergütung erst ab Bearbeiten', () => {
    expect(allowsAreas(LOOKUP, OFFICE)).toBe(false)
    expect(allowsAreas(LOOKUP, { PAYROLL: 'EDIT' })).toBe(true)
    expect(allowsAreas(LOOKUP, { CHECKLISTS: 'VIEW' })).toBe(true)
  })
})

describe('allowsPage', () => {
  it('jede geschützte Seite hat eine Bereichszuordnung (oder das Backend entscheidet)', () => {
    for (const path of Object.keys(PAGE_ACCESS)) {
      expect(PAGE_AREAS[path] !== undefined || BACKEND_DECIDES.has(path), path).toBe(true)
    }
  })
  it('Lohnbüro (nur lesen) sieht nur die Lohnbuchhaltung', () => {
    const flags = { ...HR, canPayroll: true, perms: OFFICE }
    expect(allowsPage('/lohnbuchhaltung', flags)).toBe(true)
    expect(allowsPage('/', flags)).toBe(false)
    for (const path of ['/mitarbeiter', '/lohn-export', '/zu-klaeren', '/einstellungen', '/monatsabschluss']) {
      expect(allowsPage(path, flags), path).toBe(false)
    }
  })
  it('Zeiten-Rolle sieht Anwesenheit und Zu klären, aber keine Auswertungen', () => {
    const flags = { ...HR, perms: { TIME: 'EDIT' } as Perms }
    expect(allowsPage('/uebersicht', flags)).toBe(true)
    expect(allowsPage('/zu-klaeren', flags)).toBe(true)
    expect(allowsPage('/mitarbeiter', flags)).toBe(true)
    expect(allowsPage('/auswertungen', flags)).toBe(false)
  })
  it('die Rolle bleibt maßgeblich: Führungskraft ohne Monatsabschluss', () => {
    expect(allowsPage('/monatsabschluss', { isAdmin: false, isFullHr: false, canPayroll: false })).toBe(false)
    expect(allowsPage('/monatsabschluss', HR)).toBe(true)
  })
  it('Lohnbuchhaltung verlangt „Vergütung & Lohn“', () => {
    expect(allowsPage('/lohnbuchhaltung', HR)).toBe(false)
    expect(allowsPage('/lohnbuchhaltung', { ...HR, canPayroll: true })).toBe(true)
    expect(allowsPage('/lohnbuchhaltung', { ...HR, canPayroll: true, perms: { TIME: 'EDIT' } })).toBe(false)
  })
  it('Startseite für eigene Rollen mit Tagesgeschäft', () => {
    expect(allowsPage('/', { ...HR, perms: { ABSENCES: 'VIEW' } })).toBe(true)
    expect(allowsPage('/', HR)).toBe(true)
  })
  it('Bereiche sind vollständig', () => {
    expect(AREAS).toHaveLength(12)
    expect(AREAS).toContain('RECRUITING')
  })
})

describe('allowsPage mit Schaltern und vom Backend entschiedenen Seiten', () => {
  const SUPERVISOR = { isAdmin: false, isFullHr: false, canPayroll: false }
  it('Schalter öffnet „Analysen“ für Führungskräfte, andere Seiten nicht', () => {
    expect(allowsPage('/auswertungen', SUPERVISOR)).toBe(false)
    expect(allowsPage('/auswertungen', SUPERVISOR, { custom_reports_enabled: true })).toBe(true)
    expect(allowsPage('/lohn-export', SUPERVISOR, { custom_reports_enabled: true })).toBe(false)
    // Projektzeiten öffnen „Analysen“ ebenso (einer der Schalter genügt)
    expect(allowsPage('/auswertungen', SUPERVISOR, { project_times_enabled: true })).toBe(true)
    expect(allowsPage('/auswertungen', SUPERVISOR, { custom_reports_enabled: false, project_times_enabled: false })).toBe(false)
  })
  it('eigene Rolle: Schalter ersetzt nicht den Bereich', () => {
    const timeOnly = { ...HR, perms: { TIME: 'EDIT' } as Perms }
    expect(allowsPage('/auswertungen', timeOnly, { custom_reports_enabled: true })).toBe(false)
    expect(allowsPage('/auswertungen', { ...HR, perms: { REPORTS: 'VIEW' } as Perms })).toBe(true)
  })
  it('Hinweise und Recruiting entscheidet das Backend – keine Bereichsprüfung', () => {
    const timeOnly = { ...HR, perms: { TIME: 'VIEW' } as Perms }
    expect(allowsPage('/hinweise', timeOnly)).toBe(true)
    expect(allowsPage('/recruiting', timeOnly)).toBe(true)
    expect(allowsPage('/recruiting', SUPERVISOR)).toBe(true)
  })
  it('pageAllowed ist dieselbe Funktion', async () => {
    const access = await import('./access')
    expect(access.pageAllowed).toBe(access.allowsPage)
  })
})
