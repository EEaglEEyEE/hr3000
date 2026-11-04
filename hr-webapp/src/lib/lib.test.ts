import { describe, expect, it } from 'vitest'
import type { TimesheetDay } from '../api/queries/timesheets'
import { dayCellClassName, dayCellStyle, dayCellTooltip } from './dayCellStyle'
import { addDaysIsoDate, formatDate, formatMinutesAsHours, monthRange, mondayOfWeek } from './format'

function day(overrides: Partial<TimesheetDay> = {}): TimesheetDay {
  return {
    work_date: '2026-10-21',
    target_minutes: 480,
    actual_minutes: null,
    status: 'OPEN_MISSING_PUNCH',
    absence_type: null,
    absence_type_id: null,
    is_birthday: false,
    exceeds_max_daily_minutes: false,
    flags: [],
    reviewed: false,
    ...overrides,
  }
}

describe('formatMinutesAsHours', () => {
  it.each([
    [0, '0:00'],
    [5, '+0:05'],
    [60, '+1:00'],
    [-1, '-0:01'],
    [-90, '-1:30'],
    [1439, '+23:59'],
    [6000, '+100:00'],
    [null, '–'],
    [undefined, '–'],
  ])('%s Minuten -> %s', (minutes, expected) => {
    expect(formatMinutesAsHours(minutes)).toBe(expected)
  })
})

describe('Datumsrechnung', () => {
  it('rechnet Tage über Monats-, Jahres- und Zeitumstellungsgrenzen', () => {
    expect(addDaysIsoDate('2026-10-31', 1)).toBe('2026-11-01')
    expect(addDaysIsoDate('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDaysIsoDate('2026-03-01', -1)).toBe('2026-02-28')
    expect(addDaysIsoDate('2028-03-01', -1)).toBe('2028-02-29') // Schaltjahr
    expect(addDaysIsoDate('2026-10-24', 2)).toBe('2026-10-26') // Umstellung auf Winterzeit am 25.10.
    expect(addDaysIsoDate('2026-03-28', 2)).toBe('2026-03-30') // Umstellung auf Sommerzeit am 29.03.
  })

  it('findet den Montag der Woche, auch für Sonntag und über den Jahreswechsel', () => {
    expect(mondayOfWeek('2026-10-21')).toBe('2026-10-19')
    expect(mondayOfWeek('2026-10-19')).toBe('2026-10-19')
    expect(mondayOfWeek('2026-10-25')).toBe('2026-10-19')
    expect(mondayOfWeek('2027-01-01')).toBe('2026-12-28')
  })

  it('liefert den ganzen Monat inkl. Februar im Schaltjahr', () => {
    expect(monthRange('2026-10')).toEqual({ from: '2026-10-01', to: '2026-10-31' })
    expect(monthRange('2026-02')).toEqual({ from: '2026-02-01', to: '2026-02-28' })
    expect(monthRange('2028-02')).toEqual({ from: '2028-02-01', to: '2028-02-29' })
  })

  it('zeigt ein Datum unabhängig von der Zeitzone des Browsers', () => {
    expect(formatDate('2026-10-21')).toBe('21.10.2026')
    expect(formatDate('2027-01-01')).toBe('1.1.2027')
  })
})

describe('Tagesfarben', () => {
  it.each([
    ['PRESENT', 'bg-sky-100'],
    ['ON_BREAK', 'bg-orange-100'],
    ['ON_ERRAND', 'bg-violet-100'],
    ['COMPLETE', 'bg-emerald-100'],
    ['ERROR', 'bg-red-100'],
    ['HOLIDAY', 'bg-teal-100'],
    ['PLANNED_OFF', 'bg-indigo-100'],
    ['OPEN_MISSING_PUNCH', 'bg-slate-50'],
  ] as const)('%s -> %s', (status, color) => {
    expect(dayCellClassName(day({ status }))).toContain(color)
  })

  it('markiert Sonderfälle orange, bis sie geklärt sind', () => {
    const flagged = day({ status: 'COMPLETE', flags: ['UNPLANNED_WORK'] })
    expect(dayCellClassName(flagged)).toContain('ring-amber-500')
    expect(dayCellTooltip(flagged)).toContain('zu klären: Außerplanmäßig gestempelt')
    const reviewed = { ...flagged, reviewed: true }
    expect(dayCellClassName(reviewed)).not.toContain('ring-amber-500')
    expect(dayCellTooltip(reviewed)).toContain('geklärt')
  })

  it('zeigt unbekannte Sonderfall-Codes trotzdem an', () => {
    expect(dayCellTooltip(day({ status: 'COMPLETE', actual_minutes: 480, flags: ['NEU_IM_BACKEND'] }))).toContain('NEU_IM_BACKEND')
  })

  it('nutzt die Farbe einer eigenen Abwesenheitsart', () => {
    const types = new Map([
      [9, { id: 9, name: 'Berufsschule', color: '#2563eb', category: 'SPECIAL_LEAVE', requires_approval: false, employee_can_request: false, certificate_from_day: null, active: true, sort_order: 9 }],
    ]) as Parameters<typeof dayCellStyle>[1]
    const absence = day({ status: 'ABSENCE', absence_type: 'SPECIAL_LEAVE', absence_type_id: 9 })
    expect(dayCellStyle(absence, types)).toEqual({ backgroundColor: '#2563eb33', boxShadow: 'inset 0 -3px 0 #2563eb' })
    expect(dayCellTooltip(absence, types)).toBe('Berufsschule')
    // Gelöschte/unbekannte Art: Standardfarbe der Kategorie, kein Absturz
    expect(dayCellStyle(day({ status: 'ABSENCE', absence_type: 'SICK', absence_type_id: 404 }), types)).toBeUndefined()
    expect(dayCellClassName(day({ status: 'ABSENCE', absence_type: 'SICK', absence_type_id: 404 }), types)).toContain('bg-amber-100')
  })

  it('beschreibt Tage ohne Stempelung und Dienstgang im Tooltip', () => {
    expect(dayCellTooltip(day())).toBe('Keine Stempelung')
    expect(dayCellTooltip(day({ status: 'ON_ERRAND' }))).toBe('Dienstgang (zählt als Arbeitszeit)')
    expect(dayCellTooltip(day({ status: 'COMPLETE', actual_minutes: 495 }))).toBe('Ist +8:15')
    expect(dayCellTooltip(undefined)).toBeUndefined()
  })
})
