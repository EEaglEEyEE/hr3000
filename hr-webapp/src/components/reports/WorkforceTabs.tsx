/** Feste Auswertungen „Abwesenheitsquote“ und „Köpfe und Vollzeitstellen (FTE)“ (Admin/HR). */
import { useState } from 'react'
import { useAbsenceRateQuery, useHeadcountQuery, type AbsenceCategory } from '../../api/queries/reports'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { downloadCsv } from '../../lib/csv'
import { currentYearMonth, formatDate, monthRange } from '../../lib/format'
import { ABSENCE_TYPE_LABELS } from '../../lib/labels'
import { monthLabel, shiftMonth } from '../../lib/reportFormat'

// Arbeitszeit und Feiertag sind keine Fehlzeiten (Backend lehnt sie ab)
const RATE_CATEGORIES = (Object.keys(ABSENCE_TYPE_LABELS) as AbsenceCategory[]).filter(
  (c) => c !== 'WORK_TIME' && c !== 'PUBLIC_HOLIDAY',
)
const DEFAULT_CATEGORIES: AbsenceCategory[] = ['SICK', 'CHILD_SICK']

const number = (value: number, digits = 1) => value.toLocaleString('de-DE', { maximumFractionDigits: digits })
const percent = (value: number | null) => (value === null ? '–' : `${number(value, 2)} %`)

function MonthRangeInputs({
  from,
  to,
  onFrom,
  onTo,
}: {
  from: string
  to: string
  onFrom: (value: string) => void
  onTo: (value: string) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label className="flex items-center gap-2">
        Von
        <Input type="month" className="w-40" aria-label="Von Monat" value={from} onChange={(e) => e.target.value && onFrom(e.target.value)} />
      </label>
      <label className="flex items-center gap-2">
        bis
        <Input type="month" className="w-40" aria-label="Bis Monat" value={to} onChange={(e) => e.target.value && onTo(e.target.value)} />
      </label>
    </div>
  )
}

function useMonthRange(months: number) {
  const current = currentYearMonth()
  const [from, setFrom] = useState(shiftMonth(current, -(months - 1)))
  const [to, setTo] = useState(current)
  return { from, to, setFrom, setTo, dateFrom: monthRange(from).from, dateTo: monthRange(to).to }
}

export function AbsenceRateTab() {
  const range = useMonthRange(12)
  const [categories, setCategories] = useState<AbsenceCategory[]>(DEFAULT_CATEGORIES)
  const query = useAbsenceRateQuery(range.dateFrom, range.dateTo, categories)
  const report = query.data

  function toggle(category: AbsenceCategory, checked: boolean) {
    setCategories((current) => (checked ? [...current, category] : current.filter((c) => c !== category)))
  }

  function exportCsv() {
    if (!report) return
    const header = ['Bereich', ...report.months.map((m) => m.month), 'Gesamt']
    const line = (name: string, cells: { rate_percent: number | null }[], total: { rate_percent: number | null }) => [
      name,
      ...cells.map((c) => c.rate_percent),
      total.rate_percent,
    ]
    downloadCsv(`abwesenheitsquote_${range.from}_${range.to}.csv`, header, [
      line('Gesamt', report.months, report.total),
      ...report.departments.map((d) => line(d.name, d.months, d.total)),
    ])
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <MonthRangeInputs from={range.from} to={range.to} onFrom={range.setFrom} onTo={range.setTo} />
        {report && (
          <Button variant="outline" size="sm" onClick={exportCsv}>
            CSV exportieren
          </Button>
        )}
      </div>
      <fieldset className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <legend className="mb-1 text-slate-600">Kategorien</legend>
        {RATE_CATEGORIES.map((category) => (
          <label key={category} className="flex items-center gap-1.5">
            <input type="checkbox" checked={categories.includes(category)} onChange={(e) => toggle(category, e.target.checked)} />
            {ABSENCE_TYPE_LABELS[category]}
          </label>
        ))}
      </fieldset>
      <p className="text-sm text-slate-500">
        Abwesenheitstage der gewählten Kategorien (genehmigt, halbe Tage zählen halb) geteilt durch die Soll-Arbeitstage laut
        Arbeitszeitmodell ohne Feiertage. Gezählt wird höchstens bis heute. Abteilung nach heutiger Zuordnung.
      </p>
      {categories.length === 0 && <p className="text-sm text-amber-700">Bitte mindestens eine Kategorie wählen.</p>}
      {query.isLoading && <p className="text-slate-500">Lädt…</p>}
      {query.isError && <p className="text-sm text-red-600">{query.error.message}</p>}
      {report && (
        <>
          {report.through && report.through < report.date_to && (
            <p className="text-sm text-slate-500">Gerechnet bis {formatDate(report.through)}.</p>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Bereich</TableHead>
                {report.months.map((m) => (
                  <TableHead key={m.month} className="whitespace-nowrap">
                    {monthLabel(m.month)}
                  </TableHead>
                ))}
                <TableHead>Gesamt</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[{ name: 'Gesamt', months: report.months, total: report.total, key: 'total' }, ...report.departments.map((d) => ({ ...d, key: String(d.department_id) }))].map(
                (row) => (
                  <TableRow key={row.key}>
                    <TableCell className={row.key === 'total' ? 'font-semibold' : 'font-medium'}>{row.name}</TableCell>
                    {row.months.map((cell) => (
                      <TableCell
                        key={cell.month}
                        className="whitespace-nowrap"
                        title={`${number(cell.absence_days)} von ${cell.workdays} Soll-Arbeitstagen`}
                      >
                        {percent(cell.rate_percent)}
                      </TableCell>
                    ))}
                    <TableCell className="whitespace-nowrap font-semibold" title={`${number(row.total.absence_days)} von ${row.total.workdays} Soll-Arbeitstagen`}>
                      {percent(row.total.rate_percent)}
                    </TableCell>
                  </TableRow>
                ),
              )}
            </TableBody>
          </Table>
        </>
      )}
    </div>
  )
}

export function HeadcountTab() {
  const range = useMonthRange(12)
  const query = useHeadcountQuery(range.dateFrom, range.dateTo)
  const report = query.data

  function exportCsv() {
    if (!report) return
    const names = report.departments.map((d) => d.name)
    downloadCsv(
      `koepfe_fte_${range.from}_${range.to}.csv`,
      ['Monat', 'Stichtag', 'Köpfe', 'FTE', 'Zugänge', 'Abgänge', ...names.flatMap((n) => [`${n} Köpfe`, `${n} FTE`])],
      report.months.map((m) => [
        m.month,
        formatDate(m.as_of),
        m.headcount,
        m.fte,
        m.joiners,
        m.leavers,
        ...report.departments.flatMap((d) => {
          const cell = m.departments.find((c) => c.department_id === d.department_id)
          return [cell?.headcount ?? 0, cell?.fte ?? 0]
        }),
      ]),
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <MonthRangeInputs from={range.from} to={range.to} onFrom={range.setFrom} onTo={range.setTo} />
        {report && (
          <Button variant="outline" size="sm" onClick={exportCsv}>
            CSV exportieren
          </Button>
        )}
      </div>
      {query.isLoading && <p className="text-slate-500">Lädt…</p>}
      {query.isError && <p className="text-sm text-red-600">{query.error.message}</p>}
      {report && (
        <>
          <p className="text-sm text-slate-500">
            Stand jeweils zum Monatsende laut Ein- und Austritt. FTE = Wochenstunden / {number(report.full_time_weekly_hours, 2)} Stunden
            {report.full_time_from_settings ? ' (Standard-Arbeitszeit der Firma)' : ' (keine Standard-Arbeitszeit hinterlegt)'}; „nach
            Aufwand“ zählt als Kopf mit 0 FTE, ohne Arbeitszeitmodell als Vollzeit. Abteilung nach heutiger Zuordnung.
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Monat</TableHead>
                <TableHead>Köpfe</TableHead>
                <TableHead>FTE</TableHead>
                <TableHead>Zugänge</TableHead>
                <TableHead>Abgänge</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.months.map((m) => (
                <TableRow key={m.month}>
                  <TableCell className="whitespace-nowrap">{monthLabel(m.month)}</TableCell>
                  <TableCell>{m.headcount}</TableCell>
                  <TableCell>{number(m.fte, 2)}</TableCell>
                  <TableCell>{m.joiners || '–'}</TableCell>
                  <TableCell>{m.leavers || '–'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {report.departments.length > 0 && (
            <>
              <h2 className="text-sm font-semibold text-slate-700">Je Abteilung (Köpfe / FTE)</h2>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Abteilung</TableHead>
                    {report.months.map((m) => (
                      <TableHead key={m.month} className="whitespace-nowrap">
                        {monthLabel(m.month)}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.departments.map((d) => (
                    <TableRow key={String(d.department_id)}>
                      <TableCell className="font-medium">{d.name}</TableCell>
                      {report.months.map((m) => {
                        const cell = m.departments.find((c) => c.department_id === d.department_id)
                        return (
                          <TableCell key={m.month} className="whitespace-nowrap">
                            {cell ? `${cell.headcount} / ${number(cell.fte, 2)}` : '–'}
                          </TableCell>
                        )
                      })}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </>
      )}
    </div>
  )
}
