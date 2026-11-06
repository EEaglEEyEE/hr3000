import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CakeSlice, CalendarClock, CalendarHeart, TreePalm } from 'lucide-react'
import { useCorrectionRequestsQuery } from '../../api/queries/correctionRequests'
import { usePendingAbsencesQuery } from '../../api/queries/absences'
import {
  DASHBOARD_RANGES as RANGES,
  DASHBOARD_RANGE_KEY as RANGE_KEY,
  initialDashboardRange as initialRange,
  useDashboardQuery,
  type Dashboard as DashboardData,
  type DashboardEvent,
} from '../../api/queries/dashboard'
import { ApiError } from '../../api/client'
import { useOwnPunchMutation } from '../../api/queries/punches'
import { useMonthlyCapsQuery, useOpenDaysCount } from '../../api/queries/timesheets'
import { useAuth } from '../../auth/AuthContext'
import { formatDate, formatMinutesAsHours } from '../../lib/format'
import { DAY_STATUS_LABELS, PUNCH_TYPE_LABELS } from '../../lib/labels'
import { cn } from '../../lib/utils'

/** Startseite: eigene Salden/Zeiten, für HR wer heute da ist, und die nächsten Termine. */

export function Dashboard() {
  const [days, setDays] = useState(initialRange)
  const query = useDashboardQuery(days)
  const { hasHrAccess } = useAuth()
  if (query.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (query.isError || !query.data) return <p className="text-red-600">Übersicht konnte nicht geladen werden.</p>
  const data = query.data

  return (
    <div className="flex flex-col gap-4">
      {data.me?.portal_punching && <PortalPunchCard me={data.me} />}
      {!data.me && hasHrAccess && data.portal_punching_enabled && (
        <div className="rounded-md border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
          <p className="font-medium">Stempeln ist mit diesem Konto nicht möglich</p>
          <p className="mt-1">
            Dieses Admin-Konto gehört zu keinem Mitarbeiter. Zum Stempeln am eigenen Mitarbeiter (Mitarbeiter →
            Bearbeiten) eine Login-E-Mail und ggf. die Rolle „Admin“ hinterlegen und sich dann damit anmelden – so
            hast du Admin-Rechte und die Stempel-Karte in einem Login.
          </p>
        </div>
      )}
      {data.me && <MyFigures me={data.me} />}
      {hasHrAccess && <HrTodo requestsEnabled={data.absence_requests_enabled ?? true} />}
      <div className="grid items-start gap-4 lg:grid-cols-2">
        {data.team && <TeamToday team={data.team} />}
        <Upcoming
          events={data.events}
          days={days}
          horizonDate={data.horizon_date ?? null}
          onDaysChange={(value) => {
            setDays(value)
            try {
              localStorage.setItem(RANGE_KEY, String(value))
            } catch {
              // ohne Speicher gilt die Auswahl nur bis zum Neuladen
            }
          }}
        />
      </div>
    </div>
  )
}

function Tile({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'good' | 'bad' }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-slate-200 bg-white p-4">
      <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</span>
      <span
        className={cn(
          'text-2xl font-semibold text-slate-900',
          tone === 'good' && 'text-emerald-600',
          tone === 'bad' && 'text-red-600',
        )}
      >
        {value}
      </span>
      {hint && <span className="text-xs text-slate-500">{hint}</span>}
    </div>
  )
}

function MyFigures({ me }: { me: NonNullable<DashboardData['me']> }) {
  const weekDelta = me.week_actual_minutes - me.week_target_minutes
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-slate-900">Hallo {me.first_name}</h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {me.on_demand ? (
          <Tile
            label="Diesen Monat"
            value={`${formatMinutesAsHours(me.month_actual_minutes ?? 0).replace('+', '')} Std.`}
            tone={me.monthly_cap_minutes && (me.month_actual_minutes ?? 0) > me.monthly_cap_minutes ? 'bad' : undefined}
            hint={
              me.monthly_cap_minutes
                ? `Grenze ${formatMinutesAsHours(me.monthly_cap_minutes).replace('+', '')} Std. · Abrechnung nach Ist-Stunden`
                : 'Abrechnung nach Ist-Stunden'
            }
          />
        ) : (
        <Tile
          label="Gleitzeitsaldo"
          value={`${formatMinutesAsHours(me.balance_minutes)} Std.`}
          tone={me.balance_minutes < 0 ? 'bad' : 'good'}
          hint={me.balance_date ? `Stand ${formatDate(me.balance_date)}` : undefined}
        />
        )}
        <Tile
          label={`Resturlaub ${me.vacation_year}`}
          value={`${me.vacation_remaining_days.toLocaleString('de-DE')} Tage`}
          tone={me.vacation_remaining_days < 0 ? 'bad' : undefined}
          hint={
            me.vacation_expiring_days > 0 && me.vacation_expiry_date
              ? `${me.vacation_expiring_days.toLocaleString('de-DE')} Tage verfallen nach ${formatDate(me.vacation_expiry_date)}`
              : undefined
          }
        />
        <Tile
          label="Heute"
          value={me.today_status ? DAY_STATUS_LABELS[me.today_status] : 'Nicht gestempelt'}
          hint={me.today_times || undefined}
        />
        <Tile
          label="Diese Woche"
          value={`${formatMinutesAsHours(me.week_actual_minutes).replace('+', '')} Std.`}
          hint={
            me.on_demand
              ? 'nach Aufwand, ohne Soll'
              : `Soll bisher ${formatMinutesAsHours(me.week_target_minutes).replace('+', '')} Std. (${formatMinutesAsHours(weekDelta)})`
          }
        />
      </div>
      {(me.pending_absences > 0 || me.pending_corrections > 0) && (
        <p className="text-sm text-amber-700">
          Offen: {me.pending_absences > 0 && `${me.pending_absences} Abwesenheitsantrag/-anträge`}
          {me.pending_absences > 0 && me.pending_corrections > 0 && ', '}
          {me.pending_corrections > 0 && `${me.pending_corrections} Korrekturantrag/-anträge`} – warten auf Entscheidung.
        </p>
      )}
    </div>
  )
}

function HrTodo({ requestsEnabled }: { requestsEnabled: boolean }) {
  const { isFullHr } = useAuth()
  const openDays = useOpenDaysCount()
  const pendingAbsences = usePendingAbsencesQuery().data?.length ?? 0
  const corrections = useCorrectionRequestsQuery('PENDING', isFullHr).data?.length ?? 0
  const capsExceeded = (useMonthlyCapsQuery().data ?? []).filter((row) => row.exceeded).length
  const items = [
    { to: '/zu-klaeren', label: 'Zu klären', count: openDays + capsExceeded + (isFullHr ? corrections : 0) },
    { to: '/zu-klaeren/urlaubsantraege', label: 'Urlaubsanträge', count: pendingAbsences },
  ].filter((item) => item.label !== 'Urlaubsanträge' || requestsEnabled || item.count > 0)
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {items.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          className="flex items-center justify-between rounded-md border border-slate-200 bg-white p-4 hover:bg-slate-50"
        >
          <span className="font-medium text-slate-800">{item.label}</span>
          <span
            className={cn(
              'min-w-8 rounded-full px-2 text-center text-lg font-semibold leading-8',
              item.count > 0 ? 'bg-red-600 text-white' : 'bg-slate-100 text-slate-500',
            )}
          >
            {item.count}
          </span>
        </Link>
      ))}
    </div>
  )
}

function TeamToday({ team }: { team: NonNullable<DashboardData['team']> }) {
  const groups = [
    { title: 'Anwesend', people: team.present, dot: 'bg-sky-500' },
    { title: 'In Pause', people: team.on_break, dot: 'bg-orange-500' },
    { title: 'Dienstgang', people: team.on_errand ?? [], dot: 'bg-violet-500' },
    { title: 'Abwesend', people: team.absent, dot: 'bg-slate-400' },
    // Dienstgang nur zeigen, wenn gerade jemand unterwegs ist (Funktion ist standardmäßig aus).
  ].filter((group) => group.title !== 'Dienstgang' || group.people.length > 0)
  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between">
        <p className="font-medium text-slate-900">Heute</p>
        <Link to="/uebersicht" className="text-sm text-sky-700 hover:underline">
          Anwesenheit →
        </Link>
      </div>
      {groups.map((group) => (
        <div key={group.title} className="flex flex-col gap-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {group.title} ({group.people.length})
          </p>
          {group.people.length === 0 ? (
            <p className="text-sm text-slate-400">–</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {group.people.map((person) => (
                <Link
                  key={person.employee_id}
                  to={`/employees/${person.employee_id}`}
                  className="flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-0.5 text-sm text-slate-700 hover:bg-slate-50"
                  title={person.detail ?? undefined}
                >
                  <span
                    className={cn('h-2 w-2 rounded-full', !person.color && group.dot)}
                    style={person.color ? { backgroundColor: person.color } : undefined}
                  />
                  {person.name}
                  {person.detail && <span className="text-xs text-slate-400">{person.detail}</span>}
                </Link>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function dayLabel(iso: string): string {
  const today = new Date()
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  const tomorrow = new Date(today.getTime() + 86_400_000)
  const tomorrowIso = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`
  if (iso === todayIso) return 'Heute'
  if (iso === tomorrowIso) return 'Morgen'
  const weekday = new Date(`${iso}T00:00:00Z`).toLocaleDateString('de-DE', { weekday: 'short', timeZone: 'UTC' })
  return `${weekday} ${formatDate(iso)}`
}

const EVENT_ICON = {
  HOLIDAY: CalendarHeart,
  ABSENCE: TreePalm,
  PENDING_ABSENCE: CalendarClock,
  BIRTHDAY: CakeSlice,
} as const

function Upcoming({
  events,
  days,
  horizonDate,
  onDaysChange,
}: {
  events: DashboardEvent[]
  days: number
  horizonDate: string | null
  onDaysChange: (days: number) => void
}) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-slate-900">Nächste Termine</p>
        <div className="flex gap-0.5 rounded-md bg-slate-100 p-0.5" role="radiogroup" aria-label="Zeitraum">
          {RANGES.map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={days === value}
              onClick={() => onDaysChange(value)}
              className={cn(
                'rounded px-2 py-0.5 text-xs font-medium text-slate-500 hover:text-slate-900',
                days === value && 'bg-white text-slate-900 shadow-sm',
              )}
            >
              {value} Tage
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Feiertage, Abwesenheiten (auch beantragte) und Geburtstage von heute
        {horizonDate ? ` bis ${formatDate(horizonDate)}` : ''}.
      </p>
      {events.length === 0 && <p className="text-sm text-slate-400">In diesem Zeitraum steht nichts an.</p>}
      <div className="flex flex-col divide-y divide-slate-100">
        {events.map((event, index) => {
          const Icon = EVENT_ICON[event.kind]
          return (
            <div key={index} className="flex items-center gap-3 py-2 text-sm">
              <span className="w-28 shrink-0 text-slate-500">{dayLabel(event.date)}</span>
              <Icon
                className={cn(
                  'h-4 w-4 shrink-0',
                  event.kind === 'HOLIDAY' && 'text-teal-600',
                  event.kind === 'BIRTHDAY' && 'text-pink-500',
                  event.kind === 'PENDING_ABSENCE' && 'text-amber-500',
                )}
                style={event.kind === 'ABSENCE' && event.color ? { color: event.color } : undefined}
              />
              <span className="flex-1 text-slate-800">
                {event.employee_name && <span className="font-medium">{event.employee_name}: </span>}
                {event.title}
                {event.date_to && <span className="text-slate-500"> bis {formatDate(event.date_to)}</span>}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

type PunchKind = 'COME' | 'GO' | 'BREAK_START' | 'BREAK_END' | 'ERRAND_START' | 'ERRAND_END'

const PUNCH_BUTTON_CLASS: Record<PunchKind, string> = {
  COME: 'bg-emerald-600 hover:bg-emerald-500',
  GO: 'bg-red-600 hover:bg-red-500',
  BREAK_START: 'bg-amber-600 hover:bg-amber-500',
  BREAK_END: 'bg-sky-600 hover:bg-sky-500',
  ERRAND_START: 'bg-violet-600 hover:bg-violet-500',
  ERRAND_END: 'bg-violet-600 hover:bg-violet-500',
}

/** Stempeln über den Web-Login: zeigt nur die Aktionen, die zum aktuellen Stand passen. */
function PortalPunchCard({ me }: { me: NonNullable<DashboardData['me']> }) {
  const punch = useOwnPunchMutation()
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const status = me.today_status
  const actions: PunchKind[] =
    status === 'PRESENT'
      ? (['GO', ...(me.break_buttons ? ['BREAK_START'] : []), ...(me.errand_buttons ? ['ERRAND_START'] : [])] as PunchKind[])
      : status === 'ON_BREAK'
        ? ['BREAK_END']
        : status === 'ON_ERRAND'
          ? ['ERRAND_END']
          : status === 'ERROR'
            ? ['COME', 'GO']
            : ['COME']

  async function handle(kind: PunchKind) {
    setError(null)
    setMessage(null)
    try {
      const result = await punch.mutateAsync(kind)
      const time = new Date(result.timestamp_utc.endsWith('Z') ? result.timestamp_utc : `${result.timestamp_utc}Z`)
      setMessage(`${PUNCH_TYPE_LABELS[kind]} um ${time.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} erfasst.`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Stempeln fehlgeschlagen.')
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium text-slate-900">Stempeln (Home-Office / unterwegs)</p>
        <span className="text-sm text-slate-500">
          {status ? DAY_STATUS_LABELS[status] : 'Heute noch nicht gestempelt'}
          {me.today_times ? ` · ${me.today_times}` : ''}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {actions.map((kind) => (
          <button
            key={kind}
            type="button"
            disabled={punch.isPending}
            onClick={() => void handle(kind)}
            className={cn('rounded-lg px-5 py-3 text-base font-semibold text-white disabled:opacity-50', PUNCH_BUTTON_CLASS[kind])}
          >
            {PUNCH_TYPE_LABELS[kind]}
          </button>
        ))}
      </div>
      {status === 'ERROR' && (
        <p className="text-sm text-amber-700">Die heutigen Buchungen sind widersprüchlich – bitte eine Korrektur beantragen.</p>
      )}
      {message && <p className="text-sm text-emerald-700">{message}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <p className="text-xs text-slate-400">Es gilt die aktuelle Uhrzeit des Servers.</p>
    </div>
  )
}
