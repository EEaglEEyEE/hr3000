import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AlertCircle, BarChart3, CalendarDays, CalendarRange, ClipboardCheck, FileSpreadsheet, House, KeyRound, LayoutGrid, ListChecks, LogOut, Menu, Network, PanelLeftClose, PanelLeftOpen, Settings, ShieldCheck, UserCircle, Users, X, type LucideIcon } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { cn } from '../../lib/utils'
import { allows, PAGE_ACCESS } from '../../lib/access'
import { useFeaturesQuery } from '../../api/queries/workTimeModel'
import { useCorrectionRequestsQuery } from '../../api/queries/correctionRequests'
import { usePendingAbsencesQuery } from '../../api/queries/absences'
import { useChangeRequestsQuery } from '../../api/queries/changeRequests'
import { useBalanceLimitsQuery, useMonthlyCapsQuery, useOpenDaysCount } from '../../api/queries/timesheets'
import { BrandLogo } from './BrandLogo'
import { NotificationBell } from './NotificationBell'
import { ThemeToggle } from './ThemeToggle'
import { ChangePasswordButton } from '../account/ChangePasswordDialog'
import { TwoFactorButton } from '../account/TwoFactorDialog'
import { CancellationBanner } from '../account/AccountCancellation'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  shiftPlanning?: boolean
}

// Rechte je Seite stehen in lib/access.ts (PAGE_ACCESS) – dieselbe Quelle wie der Seitenschutz.
// Konfiguration (Standorte, Teams, Feiertage, Tablets, Pausenregeln, Schichtvorlagen, Zuschläge,
// Lohnarten, Audit-Protokoll) liegt unter „Einstellungen“.
const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: 'Tagesgeschäft',
    items: [
      { to: '/', label: 'Startseite', icon: House },
      { to: '/mitarbeiter', label: 'Mitarbeiter', icon: Users },
      { to: '/uebersicht', label: 'Anwesenheit', icon: CalendarDays },
      { to: '/team-kalender', label: 'Kalender', icon: LayoutGrid },
      { to: '/organigramm', label: 'Organigramm', icon: Network },
      { to: '/zu-klaeren', label: 'Zu klären', icon: AlertCircle },
    ],
  },
  {
    title: 'Planung & Abrechnung',
    items: [
      { to: '/schichtplan-kalender', label: 'Schichtplan-Kalender', icon: CalendarRange, shiftPlanning: true },
      { to: '/monatsabschluss', label: 'Monatsabschluss', icon: ClipboardCheck },
      { to: '/auswertungen', label: 'Analysen', icon: BarChart3 },
      { to: '/lohn-export', label: 'Lohn-Export', icon: FileSpreadsheet },
      { to: '/checklisten', label: 'On- & Offboarding', icon: ListChecks },
    ],
  },
]

const COLLAPSED_KEY = 'hr3000.sidebar_collapsed'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100',
    isActive && 'bg-slate-900 text-white hover:bg-slate-900',
  )

export function AppLayout() {
  const { logout, isAdmin, isFullHr, canPayroll, employeeId } = useAuth()
  // Zu klären (Posteingang): offene Tage, Monatsgrenzen, Urlaubsanträge und Korrekturanträge (nur
  // Admin/HR entscheidet diese).
  const openDays = useOpenDaysCount()
  const pendingCorrections = useCorrectionRequestsQuery('PENDING', isFullHr).data?.length ?? 0
  const capsExceeded =
    (useMonthlyCapsQuery().data ?? []).filter((row) => row.exceeded).length +
    (useBalanceLimitsQuery().data ?? []).filter((row) => row.exceeded).length
  const pendingAbsences = usePendingAbsencesQuery().data?.length ?? 0
  const pendingChanges = useChangeRequestsQuery(isFullHr).data?.length ?? 0
  const openCount = openDays + capsExceeded + pendingAbsences + (isFullHr ? pendingCorrections + pendingChanges : 0)
  const featuresQuery = useFeaturesQuery()
  const shiftPlanningEnabled = featuresQuery.data?.shift_planning_enabled ?? false

  const allowed = (item: NavItem) =>
    allows(PAGE_ACCESS[item.to] ?? 'all', { isAdmin, isFullHr, canPayroll }) &&
    (!item.shiftPlanning || shiftPlanningEnabled)
  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter(allowed),
  })).filter((group) => group.items.length > 0)

  // Desktop: Seitenleiste auf Symbole einklappbar (pro Browser gemerkt). Handy: Menü als Schublade.
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === '1'
    } catch {
      return false
    }
  })
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  useEffect(() => setMobileOpen(false), [location.pathname])

  function toggleCollapsed() {
    setCollapsed((current) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, current ? '0' : '1')
      } catch {
        // ohne Speicher gilt die Wahl nur bis zum Neuladen
      }
      return !current
    })
  }

  // Eingeklappt nur am Desktop – im Handy-Menü immer mit Beschriftung.
  const label = collapsed ? 'md:sr-only' : ''
  const itemClass = (state: { isActive: boolean }) => cn(linkClass(state), 'relative', collapsed && 'md:justify-center')

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <header className="sticky top-0 z-30 flex items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-2 md:hidden print:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="rounded-md p-2 text-slate-700 hover:bg-slate-100"
          aria-label="Menü öffnen"
        >
          <Menu className="h-5 w-5" />
        </button>
        <BrandLogo showTenantLogo={false} />
        <NotificationBell align="right" />
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setMobileOpen(false)} aria-hidden="true" />
      )}

      {/* Seitenleiste bleibt beim Scrollen stehen – Einstellungen/Abmelden immer unten sichtbar. */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white p-4 transition-transform duration-200',
          'md:sticky md:top-0 md:z-auto md:h-screen md:translate-x-0 md:transition-[width]',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
          collapsed ? 'md:w-16 md:px-2' : 'md:w-56',
        )}
      >
        <div className={cn('mb-4 flex items-center justify-between px-2', collapsed && 'md:flex-col md:gap-2 md:px-0')}>
          <div className={cn(collapsed && 'md:hidden')}>
            <BrandLogo />
          </div>
          {collapsed && <img src="/logo.svg" alt="HR3000" className="hidden h-8 w-8 md:block" />}
          <div className="hidden md:block">
            <NotificationBell />
          </div>
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 md:hidden"
            aria-label="Menü schließen"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav className="-mx-1 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-1">
          {groups.map((group) => (
            <div key={group.title} className="flex flex-col gap-0.5">
              {groups.length > 1 && (
                <p
                  className={cn(
                    'px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400',
                    collapsed && 'md:hidden',
                  )}
                >
                  {group.title}
                </p>
              )}
              {collapsed && <hr className="mx-2 hidden border-slate-100 md:block" />}
              {group.items.map(({ to, label: text, icon: Icon }) => (
                <NavLink key={to} to={to} end={to === '/'} className={itemClass} title={collapsed ? text : undefined}>
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className={label}>{text}</span>
                  {to === '/zu-klaeren' && openCount > 0 && (
                    <span
                      className={cn(
                        'ml-auto min-w-5 rounded-full bg-red-600 px-1.5 text-center text-xs font-semibold leading-5 text-white',
                        collapsed && 'md:absolute md:-right-1 md:-top-1 md:ml-0 md:min-w-4 md:px-1 md:text-[10px] md:leading-4',
                      )}
                      title={`${openCount} offen`}
                    >
                      {openCount > 99 ? '99+' : openCount}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="mt-3 flex flex-col gap-0.5 border-t border-slate-200 pt-3">
          {employeeId !== null && (
            <NavLink to="/mein-bereich" className={itemClass} title={collapsed ? 'Mein Bereich' : undefined}>
              <UserCircle className="h-4 w-4 shrink-0" />
              <span className={label}>Mein Bereich</span>
            </NavLink>
          )}
          {allows(PAGE_ACCESS['/einstellungen'], { isAdmin, isFullHr, canPayroll }) && (
            <NavLink to="/einstellungen" className={itemClass} title={collapsed ? 'Einstellungen' : undefined}>
              <Settings className="h-4 w-4 shrink-0" />
              <span className={label}>Einstellungen</span>
            </NavLink>
          )}
          <ThemeToggle className={cn('mb-1', collapsed && 'md:flex-col')} />
          <ChangePasswordButton
            title={collapsed ? 'Passwort ändern' : undefined}
            className={cn(
              'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900',
              collapsed && 'md:justify-center',
            )}
          >
            <KeyRound className="h-4 w-4 shrink-0" />
            <span className={label}>Passwort ändern</span>
          </ChangePasswordButton>
          <TwoFactorButton
            title="Zwei-Faktor-Anmeldung"
            className={cn(
              'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900',
              collapsed && 'md:justify-center',
            )}
          >
            <ShieldCheck className="h-4 w-4 shrink-0" />
            <span className={label}>Zwei-Faktor</span>
          </TwoFactorButton>
          <button
            type="button"
            onClick={logout}
            title={collapsed ? 'Abmelden' : undefined}
            className={cn(
              'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900',
              collapsed && 'md:justify-center',
            )}
          >
            <LogOut className="h-4 w-4 shrink-0" />
            <span className={label}>Abmelden</span>
          </button>
          <button
            type="button"
            onClick={toggleCollapsed}
            title={collapsed ? 'Menü ausklappen' : 'Menü einklappen'}
            className={cn(
              'hidden items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-400 hover:bg-slate-100 hover:text-slate-900 md:flex',
              collapsed && 'md:justify-center',
            )}
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4 shrink-0" /> : <PanelLeftClose className="h-4 w-4 shrink-0" />}
            <span className={label}>Einklappen</span>
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 bg-slate-50 p-4 md:p-6">
        <CancellationBanner />
        <Outlet />
      </main>
    </div>
  )
}
