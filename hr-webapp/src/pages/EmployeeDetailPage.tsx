import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Download, ShieldOff } from 'lucide-react'
import { downloadEmployeeDataExport } from '../api/employeeDataExport'
import { useAnonymizeEmployeeMutation, useEmployeeQuery } from '../api/queries/employees'
import { useLocationsQuery } from '../api/queries/locations'
import { useAuth } from '../auth/AuthContext'
import { hasArea, type Area, type Level } from '../lib/access'
import { ApiError } from '../api/client'
import { AbsencesTab } from '../components/absences/AbsencesTab'
import { EmployeeForm } from '../components/employees/EmployeeFormDialog'
import { PunchHistoryTab } from '../components/punches/PunchHistoryTab'
import { Button } from '../components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { CalendarTab } from '../components/timesheet/CalendarTab'
import { TimesheetTab } from '../components/timesheet/TimesheetTab'
import { ShiftPlanTab } from '../components/shiftplanning/ShiftPlanTab'
import { WorkTimeModelTab } from '../components/workTimeModel/WorkTimeModelTab'
import { EmploymentTab } from '../components/employment/EmploymentTab'
import { DocumentsTab } from '../components/documents/DocumentsTab'
import { EmployeeChecklistsTab } from '../components/checklists/EmployeeChecklistsTab'
import { MasterDataTab } from '../components/employees/MasterDataTab'
import { AttributesTab, EmployeeHistoryTab } from '../components/employees/AttributesTab'
import { MonthReportButton } from '../components/periods/MonthReportButton'
import { useFeaturesQuery } from '../api/queries/workTimeModel'

export function EmployeeDetailPage() {
  const { employeeId } = useParams<{ employeeId: string }>()
  const id = Number(employeeId)
  // ?reiter=einstellungen: direkt in den Reiter „Einstellungen“ (z. B. „Bearbeiten“ in der Mitarbeiterliste)
  const [searchParams] = useSearchParams()
  const { isAdmin, isFullHr, canPayroll, perms } = useAuth()
  // Eigene Rolle: Reiter nur für freigegebene Bereiche, Bearbeiten nur mit Stufe „Bearbeiten“
  const can = (area: Area, level: Level = 'VIEW') => hasArea(perms, area, level)
  const fileTabs = {
    masterdata: can('EMPLOYEES'),
    attributes: can('EMPLOYEES'),
    employment: can('EMPLOYEES'),
    documents: can('DOCUMENTS'),
    checklists: can('CHECKLISTS'),
    history: can('EMPLOYEES'),
  }
  const tabs = {
    punches: can('TIME'),
    calendar: can('ABSENCES') || can('TIME'),
    timesheet: can('TIME'),
    absences: can('ABSENCES'),
    worktime: can('TIME') || can('EMPLOYEES'),
    file: isFullHr && Object.values(fileTabs).some(Boolean),
    settings: isFullHr && can('EMPLOYEES', 'EDIT'),
  }
  const featuresQuery = useFeaturesQuery()
  const shiftPlanningEnabled = featuresQuery.data?.shift_planning_enabled ?? false
  const employeeQuery = useEmployeeQuery(id)
  const locationsQuery = useLocationsQuery()
  const anonymizeEmployee = useAnonymizeEmployeeMutation()
  const [exportError, setExportError] = useState<string | null>(null)
  const [anonymizeError, setAnonymizeError] = useState<string | null>(null)

  if (employeeQuery.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (employeeQuery.isError || !employeeQuery.data) {
    return <p className="text-red-600">Mitarbeiter nicht gefunden.</p>
  }

  const employee = employeeQuery.data

  async function handleDataExport() {
    setExportError(null)
    try {
      await downloadEmployeeDataExport(id)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Datenexport fehlgeschlagen.')
    }
  }

  async function handleAnonymize() {
    setAnonymizeError(null)
    if (
      !window.confirm(
        `Mitarbeiter "${employee.first_name} ${employee.last_name}" wirklich anonymisieren? Name, Login und Zugangsdaten werden unwiderruflich überschrieben. Stempelungen und Abwesenheiten bleiben erhalten.`,
      )
    ) {
      return
    }
    try {
      await anonymizeEmployee.mutateAsync(id)
    } catch (err) {
      setAnonymizeError(
        err instanceof ApiError && err.code === 'EMPLOYEE_NOT_TERMINATED'
          ? 'Nur ausgeschiedene Mitarbeiter (mit Austrittsdatum) können anonymisiert werden.'
          : 'Anonymisierung fehlgeschlagen.',
      )
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/mitarbeiter" className="mb-2 flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
            <ArrowLeft className="h-4 w-4" />
            Zurück zur Mitarbeiterliste
          </Link>
          <h1 className="text-lg font-semibold text-slate-900">
            {employee.first_name} {employee.last_name}
            <span className="ml-2 text-sm font-normal text-slate-500">{employee.employee_number}</span>
          </h1>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {(can('PERIOD_CLOSURE') || can('TIME')) && <MonthReportButton employeeId={id} />}
          {isFullHr && !perms && (
            <Button variant="outline" size="sm" onClick={handleDataExport}>
              <Download className="h-4 w-4" />
              DSGVO-Datenexport
            </Button>
          )}
          {isAdmin && !employee.anonymized_at && (
            <Button
              variant="outline"
              size="sm"
              disabled={anonymizeEmployee.isPending}
              onClick={handleAnonymize}
            >
              <ShieldOff className="h-4 w-4" />
              Anonymisieren
            </Button>
          )}
        </div>
      </div>
      {exportError && <p className="text-sm text-red-600">{exportError}</p>}
      {anonymizeError && <p className="text-sm text-red-600">{anonymizeError}</p>}
      {employee.anonymized_at && (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Dieser Mitarbeiter wurde am {new Date(employee.anonymized_at).toLocaleDateString('de-DE')}{' '}
          DSGVO-anonymisiert. Stammdaten sind unwiderruflich überschrieben, Stempelungen und
          Abwesenheiten bleiben für die Aufbewahrungsfrist erhalten.
        </p>
      )}

      {/* Arbeitszeit = Modell + Schichtplanung, Personalakte = Stammdaten, Vertrag, Dokumente …, Einstellungen = Grunddaten, Login, Rolle */}
      <Tabs
        defaultValue={
          tabs.settings && searchParams.get('reiter') === 'einstellungen'
            ? 'settings'
            : (Object.keys(tabs) as (keyof typeof tabs)[]).find((key) => tabs[key])
        }
      >
        <TabsList>
          {tabs.punches && <TabsTrigger value="punches">Zeiterfassung</TabsTrigger>}
          {tabs.calendar && <TabsTrigger value="calendar">Kalender</TabsTrigger>}
          {tabs.timesheet && <TabsTrigger value="timesheet">Überstundenkonto</TabsTrigger>}
          {tabs.absences && <TabsTrigger value="absences">Abwesenheiten</TabsTrigger>}
          {tabs.worktime && <TabsTrigger value="worktime">Arbeitszeit</TabsTrigger>}
          {tabs.file && <TabsTrigger value="file">Personalakte</TabsTrigger>}
          {tabs.settings && <TabsTrigger value="settings">Einstellungen</TabsTrigger>}
        </TabsList>
        {tabs.punches && (
          <TabsContent value="punches">
            <PunchHistoryTab employeeId={id} readOnly={!isFullHr || !can('TIME', 'EDIT')} />
          </TabsContent>
        )}
        {tabs.calendar && (
          <TabsContent value="calendar">
            <CalendarTab employeeId={id} />
          </TabsContent>
        )}
        {tabs.timesheet && (
          <TabsContent value="timesheet">
            <TimesheetTab employeeId={id} canAdjust={isFullHr && can('TIME', 'EDIT')} />
          </TabsContent>
        )}
        {tabs.absences && (
          <TabsContent value="absences">
            <AbsencesTab employeeId={id} entitlementReadOnly={!isFullHr || !can('ABSENCES', 'EDIT')} />
          </TabsContent>
        )}
        {tabs.worktime && (
          <TabsContent value="worktime">
            <div className="flex flex-col gap-8">
              <WorkTimeModelTab employeeId={id} canEdit={isFullHr && (can('TIME', 'EDIT') || can('EMPLOYEES', 'EDIT'))} />
              {shiftPlanningEnabled && (can('SHIFT_PLANNING') || can('TIME')) && (
                <section className="flex flex-col gap-3 border-t border-slate-200 pt-6">
                  <h2 className="text-base font-semibold text-slate-900">Schichtplanung</h2>
                  <ShiftPlanTab employeeId={id} readOnly={!isFullHr || !can('SHIFT_PLANNING', 'EDIT')} />
                </section>
              )}
            </div>
          </TabsContent>
        )}
        {tabs.file && (
          <TabsContent value="file">
            <Tabs defaultValue={(Object.keys(fileTabs) as (keyof typeof fileTabs)[]).find((key) => fileTabs[key])}>
              <TabsList>
                {fileTabs.masterdata && <TabsTrigger value="masterdata">Stammdaten</TabsTrigger>}
                {fileTabs.attributes && <TabsTrigger value="attributes">Weitere Angaben</TabsTrigger>}
                {fileTabs.employment && (
                  <TabsTrigger value="employment">Vertrag{canPayroll ? ' & Vergütung' : ''}</TabsTrigger>
                )}
                {fileTabs.documents && <TabsTrigger value="documents">Dokumente</TabsTrigger>}
                {fileTabs.checklists && <TabsTrigger value="checklists">On- & Offboarding</TabsTrigger>}
                {fileTabs.history && <TabsTrigger value="history">Verlauf</TabsTrigger>}
              </TabsList>
              {fileTabs.masterdata && (
                <TabsContent value="masterdata">
                  <MasterDataTab employee={employee} />
                </TabsContent>
              )}
              {fileTabs.employment && (
                <TabsContent value="employment">
                  <EmploymentTab
                    employeeId={id}
                    isAdmin={canPayroll}
                    canEditContract={can('EMPLOYEES', 'EDIT')}
                    canEditPay={can('PAYROLL', 'EDIT')}
                  />
                </TabsContent>
              )}
              {fileTabs.documents && (
                <TabsContent value="documents">
                  <DocumentsTab employeeId={id} isAdmin={isAdmin} />
                </TabsContent>
              )}
              {fileTabs.checklists && (
                <TabsContent value="checklists">
                  <EmployeeChecklistsTab employeeId={id} />
                </TabsContent>
              )}
              {fileTabs.attributes && (
                <TabsContent value="attributes">
                  <AttributesTab employeeId={id} />
                </TabsContent>
              )}
              {fileTabs.history && (
                <TabsContent value="history">
                  <EmployeeHistoryTab employeeId={id} />
                </TabsContent>
              )}
            </Tabs>
          </TabsContent>
        )}
        {tabs.settings && (
          <TabsContent value="settings">
            <EmployeeForm employee={employee} locations={locationsQuery.data ?? []} />
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
