import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useAbsenceStatsQuery,
  useAttentionQuery,
  useLaborCostsQuery,
  useOvertimeReportQuery,
  useVacationReportQuery,
} from '../api/queries/reports'
import { useAuth } from '../auth/AuthContext'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { downloadCsv } from '../lib/csv'
import { currentYearMonth, formatDate, formatDays, formatMinutesAsHours, monthRange } from '../lib/format'

const MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
const KIND_LABELS = {
  BEM: 'BEM prüfen',
  PROBATION_ENDING: 'Probezeit endet',
  FIXED_TERM_ENDING: 'Befristung endet',
  TERMINATION: 'Austritt',
} as const
const KIND_VARIANT = { BEM: 'danger', PROBATION_ENDING: 'warning', FIXED_TERM_ENDING: 'warning', TERMINATION: 'info' } as const

const money = (value: number | null | undefined) =>
  value === null || value === undefined ? '–' : value.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })

function ExportButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="outline" size="sm" onClick={onClick}>
      CSV exportieren
    </Button>
  )
}

export function ReportsPage() {
  const { isAdmin } = useAuth()
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Auswertungen</h1>
      <Tabs defaultValue="attention">
        <TabsList>
          <TabsTrigger value="attention">Handlungsbedarf</TabsTrigger>
          <TabsTrigger value="absences">Fehlzeiten</TabsTrigger>
          <TabsTrigger value="vacation">Urlaub</TabsTrigger>
          <TabsTrigger value="overtime">Überstunden</TabsTrigger>
          {isAdmin && <TabsTrigger value="costs">Lohnkosten</TabsTrigger>}
        </TabsList>
        <TabsContent value="attention">
          <AttentionTab />
        </TabsContent>
        <TabsContent value="absences">
          <AbsencesTab />
        </TabsContent>
        <TabsContent value="vacation">
          <VacationTab />
        </TabsContent>
        <TabsContent value="overtime">
          <OvertimeTab />
        </TabsContent>
        {isAdmin && (
          <TabsContent value="costs">
            <CostsTab />
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}

function AttentionTab() {
  const query = useAttentionQuery()
  const items = query.data ?? []
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-500">
        BEM-Hinweis: mehr als 6 Wochen (42 Kalendertage) Arbeitsunfähigkeit in den letzten 12 Monaten – dem Mitarbeiter ist ein
        betriebliches Eingliederungsmanagement anzubieten (§ 167 Abs. 2 SGB IX).
      </p>
      {query.isLoading && <p className="text-slate-500">Lädt…</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mitarbeiter</TableHead>
            <TableHead>Hinweis</TableHead>
            <TableHead>Datum</TableHead>
            <TableHead>Details</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item, index) => (
            <TableRow key={`${item.employee_id}-${item.kind}-${index}`}>
              <TableCell>
                <Link className="text-sky-700 hover:underline" to={`/employees/${item.employee_id}`}>
                  {item.last_name}, {item.first_name}
                </Link>
              </TableCell>
              <TableCell>
                <Badge variant={KIND_VARIANT[item.kind]}>{KIND_LABELS[item.kind]}</Badge>
              </TableCell>
              <TableCell>{item.due_date ? formatDate(item.due_date) : '–'}</TableCell>
              <TableCell className="text-slate-600">{item.detail}</TableCell>
            </TableRow>
          ))}
          {items.length === 0 && !query.isLoading && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-slate-500">
                Aktuell kein Handlungsbedarf.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}

function YearInput({ year, onChange }: { year: number; onChange: (year: number) => void }) {
  return (
    <Input type="number" className="w-28" min={2000} max={2100} value={year} onChange={(e) => e.target.value && onChange(Number(e.target.value))} />
  )
}

const ABSENCE_STAT_ROWS = [
  ['vacation_days', 'Urlaub'],
  ['sick_days', 'Krank'],
  ['child_sick_days', 'Kind krank'],
  ['special_leave_days', 'Sonderurlaub'],
  ['unpaid_days', 'Unbezahlt'],
  ['time_off_days', 'Freizeitausgleich'],
] as const

function AbsencesTab() {
  const [year, setYear] = useState(new Date().getFullYear())
  const query = useAbsenceStatsQuery(year)
  const stats = query.data
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <YearInput year={year} onChange={setYear} />
        {stats && (
          <ExportButton
            onClick={() =>
              downloadCsv(
                `fehlzeiten_${year}.csv`,
                ['Personalnummer', 'Nachname', 'Vorname', 'Urlaubstage', 'Krankheitstage', 'Sonderurlaubstage', 'Unbezahlt', 'Freizeitausgleich'],
                stats.employees.map((e) => [e.employee_number, e.last_name, e.first_name, e.vacation_days, e.sick_days, e.special_leave_days, e.unpaid_days, e.time_off_days]),
              )
            }
          />
        )}
      </div>
      {stats && (
        <>
          <p className="text-sm text-slate-600">
            Krankenquote {year}:{' '}
            <span className="font-semibold">
              {stats.sick_rate_percent === null ? '–' : `${stats.sick_rate_percent.toLocaleString('de-DE')} %`}
            </span>{' '}
            <span className="text-slate-400">
              (Näherung: Krankheitstage / (aktive Mitarbeiter × Arbeitstage Mo–Sa ohne Feiertage), {stats.active_employee_count} aktive Mitarbeiter)
            </span>
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead />
                {stats.months.map((m) => (
                  <TableHead key={m.month}>{MONTHS[m.month - 1]}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {ABSENCE_STAT_ROWS.map(([key, label]) => (
                <TableRow key={key}>
                  <TableCell className="font-medium">{label}</TableCell>
                  {stats.months.map((m) => (
                    <TableCell key={m.month}>{m[key] ? formatDays(m[key]) : '–'}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Mitarbeiter</TableHead>
                <TableHead>Urlaub</TableHead>
                <TableHead>Krank</TableHead>
                <TableHead>Sonderurlaub</TableHead>
                <TableHead>Unbezahlt</TableHead>
                <TableHead>Freizeitausgl.</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stats.employees.map((e) => (
                <TableRow key={e.employee_id}>
                  <TableCell>
                    {e.last_name}, {e.first_name}
                  </TableCell>
                  <TableCell>{formatDays(e.vacation_days)}</TableCell>
                  <TableCell>{formatDays(e.sick_days)}</TableCell>
                  <TableCell>{formatDays(e.special_leave_days)}</TableCell>
                  <TableCell>{formatDays(e.unpaid_days)}</TableCell>
                  <TableCell>{formatDays(e.time_off_days)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </div>
  )
}

function VacationTab() {
  const [year, setYear] = useState(new Date().getFullYear())
  const query = useVacationReportQuery(year)
  const rows = query.data ?? []
  const fmt = (n: number) => n.toLocaleString('de-DE', { maximumFractionDigits: 1 })
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <YearInput year={year} onChange={setYear} />
        <ExportButton
          onClick={() =>
            downloadCsv(
              `urlaub_${year}.csv`,
              ['Personalnummer', 'Nachname', 'Vorname', 'Anspruch', 'Übertrag', 'Verfallen', 'Genommen', 'Rest'],
              rows.map((r) => [r.employee_number, r.last_name, r.first_name, r.entitled_days, r.carried_over_days, r.expired_days, r.used_days, r.remaining_days]),
            )
          }
        />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mitarbeiter</TableHead>
            <TableHead>Anspruch</TableHead>
            <TableHead>Übertrag</TableHead>
            <TableHead>Verfallen</TableHead>
            <TableHead>Genommen</TableHead>
            <TableHead>Rest</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.employee_id}>
              <TableCell>
                {r.last_name}, {r.first_name}
              </TableCell>
              <TableCell>{fmt(r.entitled_days)}</TableCell>
              <TableCell>{fmt(r.carried_over_days)}</TableCell>
              <TableCell>{r.expired_days ? fmt(r.expired_days) : '–'}</TableCell>
              <TableCell>{fmt(r.used_days)}</TableCell>
              <TableCell className={r.remaining_days < 0 ? 'font-semibold text-red-600' : ''}>{fmt(r.remaining_days)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function OvertimeTab() {
  const query = useOvertimeReportQuery()
  const rows = query.data ?? []
  return (
    <div className="flex flex-col gap-3">
      <div>
        <ExportButton
          onClick={() =>
            downloadCsv(
              'ueberstunden.csv',
              ['Personalnummer', 'Nachname', 'Vorname', 'Saldo (h)', 'Stand'],
              rows.map((r) => [r.employee_number, r.last_name, r.first_name, (r.balance_minutes / 60).toFixed(2), r.as_of]),
            )
          }
        />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mitarbeiter</TableHead>
            <TableHead>Gleitzeitsaldo</TableHead>
            <TableHead>Stand</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.employee_id}>
              <TableCell>
                {r.last_name}, {r.first_name}
              </TableCell>
              <TableCell className={r.balance_minutes < 0 ? 'text-red-600' : ''}>{formatMinutesAsHours(r.balance_minutes)} h</TableCell>
              <TableCell>{r.as_of ? formatDate(r.as_of) : '–'}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function CostsTab() {
  const [yearMonth, setYearMonth] = useState(currentYearMonth())
  const { from, to } = monthRange(yearMonth)
  const query = useLaborCostsQuery(from, to, true)
  const report = query.data
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <Input type="month" className="w-44" value={yearMonth} onChange={(e) => e.target.value && setYearMonth(e.target.value)} />
        {report && (
          <ExportButton
            onClick={() =>
              downloadCsv(
                `lohnkosten_${yearMonth}.csv`,
                ['Personalnummer', 'Nachname', 'Vorname', 'Art', 'Satz', 'Stunden', 'Grundvergütung', 'Zuschläge', 'Gesamt', 'Hinweis'],
                report.rows.map((r) => [
                  r.employee_number, r.last_name, r.first_name, r.pay_type, r.rate,
                  (r.actual_minutes / 60).toFixed(2), r.base_cost, r.surcharge_cost, r.total_cost, r.note,
                ]),
              )
            }
          />
        )}
      </div>
      <p className="text-sm text-slate-500">
        Brutto ohne Arbeitgeberanteile. Jeder Abruf wird im Audit-Log protokolliert. Stundenlohn: bezahlte Stunden (inkl. Feiertag/Urlaub/Krank) × Satz plus Zuschläge.
      </p>
      {query.isError && <p className="text-red-600">Auswertung konnte nicht geladen werden.</p>}
      {report && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mitarbeiter</TableHead>
              <TableHead>Satz</TableHead>
              <TableHead>Stunden</TableHead>
              <TableHead>Grundvergütung</TableHead>
              <TableHead>Zuschläge</TableHead>
              <TableHead>Gesamt</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {report.rows.map((r) => (
              <TableRow key={r.employee_id}>
                <TableCell>
                  {r.last_name}, {r.first_name}
                  {r.note && <span className="block text-xs text-slate-400">{r.note}</span>}
                </TableCell>
                <TableCell>{r.rate === null ? '–' : `${money(r.rate)}${r.pay_type === 'HOURLY' ? ' / h' : ' / Monat'}`}</TableCell>
                <TableCell>{formatMinutesAsHours(r.actual_minutes).replace('+', '')}</TableCell>
                <TableCell>{money(r.base_cost)}</TableCell>
                <TableCell>{money(r.surcharge_cost)}</TableCell>
                <TableCell className="font-medium">{money(r.total_cost)}</TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell colSpan={5} className="text-right font-semibold">
                Summe
              </TableCell>
              <TableCell className="font-semibold">{money(report.total_cost)}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )}
    </div>
  )
}
