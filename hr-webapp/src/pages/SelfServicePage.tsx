import { LogOut } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useAbsenceRequestsEnabled } from '../api/queries/dashboard'
import { useEmployeeQuery } from '../api/queries/employees'
import { AbsencesTab } from '../components/absences/AbsencesTab'
import { Dashboard } from '../components/dashboard/Dashboard'
import { DocumentsTab } from '../components/documents/DocumentsTab'
import { PeriodClosuresSelfTab } from '../components/periods/PeriodClosuresSelfTab'
import { MonthReportButton } from '../components/periods/MonthReportButton'
import { NotificationBell } from '../components/layout/NotificationBell'
import { ThemeToggle } from '../components/layout/ThemeToggle'
import { PunchHistoryTab } from '../components/punches/PunchHistoryTab'
import { CorrectionRequestSelfCard } from '../components/punches/CorrectionRequests'
import { CalendarTab } from '../components/timesheet/CalendarTab'
import { TimesheetTab } from '../components/timesheet/TimesheetTab'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { BrandLogo } from '../components/layout/BrandLogo'
import { ShiftPlanTab } from '../components/shiftplanning/ShiftPlanTab'

export function SelfServicePage() {
  const { employeeId, logout, hasHrAccess } = useAuth()
  const employeeQuery = useEmployeeQuery(employeeId ?? undefined)
  const absenceRequestsEnabled = useAbsenceRequestsEnabled()

  if (employeeId === null) return null
  if (employeeQuery.isLoading) return <p className="p-6 text-slate-500">Lädt…</p>
  if (employeeQuery.isError || !employeeQuery.data) {
    return <p className="p-6 text-red-600">Daten konnten nicht geladen werden.</p>
  }

  const employee = employeeQuery.data

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 md:px-6 md:py-4">
        <div className="flex items-center gap-4">
          <BrandLogo />
          <div>
            <div className="text-xs text-slate-500">Mein Bereich</div>
            <div className="font-semibold text-slate-900">
              {employee.first_name} {employee.last_name}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <MonthReportButton employeeId={employeeId} />
          {hasHrAccess && (
            <Link to="/" className="text-sm text-sky-700 hover:underline">
              Zur HR-Ansicht
            </Link>
          )}
          <ThemeToggle />
          <NotificationBell />
          <button
            type="button"
            onClick={logout}
            className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-800"
          >
            <LogOut className="h-4 w-4" />
            Abmelden
          </button>
        </div>
      </header>

      <main className="p-4 md:p-6">
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Übersicht</TabsTrigger>
            <TabsTrigger value="punches">Zeiterfassung</TabsTrigger>
            <TabsTrigger value="calendar">Kalender</TabsTrigger>
            <TabsTrigger value="timesheet">Saldenübersicht</TabsTrigger>
            <TabsTrigger value="absences">Abwesenheiten</TabsTrigger>
            <TabsTrigger value="shiftplan">Schichtplanung</TabsTrigger>
            <TabsTrigger value="periods">Monatsabschluss</TabsTrigger>
            <TabsTrigger value="documents">Dokumente</TabsTrigger>
          </TabsList>
          <TabsContent value="overview">
            <Dashboard />
          </TabsContent>
          <TabsContent value="punches">
            <div className="flex flex-col gap-4">
              <CorrectionRequestSelfCard />
              <PunchHistoryTab employeeId={employeeId} readOnly />
            </div>
          </TabsContent>
          <TabsContent value="calendar">
            <CalendarTab employeeId={employeeId} />
          </TabsContent>
          <TabsContent value="timesheet">
            <TimesheetTab employeeId={employeeId} />
          </TabsContent>
          <TabsContent value="absences">
            <AbsencesTab employeeId={employeeId} readOnly allowSelfCreate={absenceRequestsEnabled} />
          </TabsContent>
          <TabsContent value="shiftplan">
            <ShiftPlanTab employeeId={employeeId} readOnly />
          </TabsContent>
          <TabsContent value="periods">
            <PeriodClosuresSelfTab employeeId={employeeId} />
          </TabsContent>
          <TabsContent value="documents">
            <DocumentsTab employeeId={employeeId} readOnly />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}
