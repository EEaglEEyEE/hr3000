import { describe, expect, it } from 'vitest'
import { automaticSupervisorText, departmentPaths } from './departments'

describe('departmentPaths', () => {
  it('baut Pfade über alle Ebenen', () => {
    const paths = departmentPaths([
      { id: 1, name: 'Vertrieb', parent_id: null },
      { id: 2, name: 'Innendienst', parent_id: 1 },
      { id: 3, name: 'Angebote', parent_id: 2 },
      { id: 4, name: 'IT' },
    ])
    expect(paths.get(1)).toBe('Vertrieb')
    expect(paths.get(3)).toBe('Vertrieb › Innendienst › Angebote')
    expect(paths.get(4)).toBe('IT')
  })

  it('übersteht verwaiste Verweise und Zyklen', () => {
    expect(departmentPaths([{ id: 2, name: 'Lager', parent_id: 99 }]).get(2)).toBe('Lager')
    const loop = departmentPaths([
      { id: 1, name: 'A', parent_id: 2 },
      { id: 2, name: 'B', parent_id: 1 },
    ])
    expect(loop.get(1)).toBe('B › A')
    expect(departmentPaths([]).size).toBe(0)
  })
})

describe('automaticSupervisorText', () => {
  const lead = (employee_id: number, name: string, role = 'HEAD', active = true) => ({ employee_id, name, role, active })
  // Vertrieb (Leitungen Tom und Nora, Stellvertretung Ina) → Innendienst (ohne Leitung); Lager ohne Leitung;
  // Werk (Leitung Alt, aber inaktiv)
  const departments = [
    { id: 1, name: 'Vertrieb', parent_id: null, leaders: [lead(10, 'Tom Teamleiter'), lead(11, 'Nora Test'), lead(12, 'Ina Vize', 'DEPUTY')] },
    { id: 2, name: 'Innendienst', parent_id: 1, leaders: [] },
    { id: 3, name: 'Lager', parent_id: null },
    { id: 4, name: 'Werk', parent_id: null, leaders: [lead(13, 'Alt Chef', 'HEAD', false)] },
    { id: 5, name: 'Chefetage', parent_id: null, leaders: [lead(20, 'Bea Boss')] },
    { id: 6, name: 'Projekt', parent_id: 5, leaders: [lead(21, 'Pia Projekt')] },
  ]

  it('nennt alle Leitungen der Abteilung oder der nächsten darüber, mit Stellvertretung', () => {
    const text = 'Automatisch: Tom Teamleiter, Nora Test (Leitung Vertrieb). Stellvertretung: Ina Vize.'
    expect(automaticSupervisorText(departments, 1, 5)).toBe(text)
    expect(automaticSupervisorText(departments, 2, 5)).toBe(text)
  })

  it('nennt die Stellvertretung nicht, wenn es die Person selbst ist', () => {
    expect(automaticSupervisorText(departments, 1, 12)).toBe('Automatisch: Tom Teamleiter, Nora Test (Leitung Vertrieb).')
  })

  it('geht für eine Leitung eine Ebene höher', () => {
    expect(automaticSupervisorText(departments, 1, 10)).toBe('Automatisch: keine (Abteilung ohne Leitung).')
    expect(automaticSupervisorText(departments, 6, 21)).toBe('Automatisch: Bea Boss (Leitung Chefetage).')
  })

  it('nimmt ohne Abteilung die Abteilung, die die Person leitet', () => {
    expect(automaticSupervisorText(departments, null, 21)).toBe('Automatisch: Bea Boss (Leitung Chefetage).')
  })

  it('ignoriert inaktive Leitungen und sagt, wenn es keine gibt', () => {
    expect(automaticSupervisorText(departments, 4, 5)).toBe('Automatisch: keine (Abteilung ohne Leitung).')
    expect(automaticSupervisorText(departments, null, 5)).toBe('Automatisch: keine (ohne Abteilung).')
    expect(automaticSupervisorText(departments, 3, 5)).toBe('Automatisch: keine (Abteilung ohne Leitung).')
    expect(automaticSupervisorText([], 99, 5)).toBe('Automatisch: keine (Abteilung ohne Leitung).')
    expect(automaticSupervisorText(departments, null, undefined)).toBe('Automatisch: keine (ohne Abteilung).')
    const loop = [
      { id: 1, name: 'A', parent_id: 2, leaders: [] },
      { id: 2, name: 'B', parent_id: 1, leaders: [] },
    ]
    expect(automaticSupervisorText(loop, 1, 5)).toBe('Automatisch: keine (Abteilung ohne Leitung).')
  })
})
