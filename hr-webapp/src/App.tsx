import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { AppLayout } from './components/layout/AppLayout'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { SuperAdminLayout } from './components/layout/SuperAdminLayout'
import { AttendanceOverviewPage } from './pages/AttendanceOverviewPage'
import { AuditLogPage } from './pages/AuditLogPage'
import { BreakRulesPage } from './pages/BreakRulesPage'
import { DevicesPage } from './pages/DevicesPage'
import { EmployeeBulkImportPage } from './pages/EmployeeBulkImportPage'
import { EmployeeDetailPage } from './pages/EmployeeDetailPage'
import { DashboardPage } from './pages/DashboardPage'
import { EmployeesPage } from './pages/EmployeesPage'
import { HolidaysPage } from './pages/HolidaysPage'
import { LocationsPage } from './pages/LocationsPage'
import { LoginPage } from './pages/LoginPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { OpenDaysPage } from './pages/OpenDaysPage'
import { PayrollExportPage } from './pages/PayrollExportPage'
import { PendingAbsencesPage } from './pages/PendingAbsencesPage'
import { SelfServicePage } from './pages/SelfServicePage'
import { SettingsPage } from './pages/SettingsPage'
import { ShiftPlanCalendarPage } from './pages/ShiftPlanCalendarPage'
import { ShiftTemplatesPage } from './pages/ShiftTemplatesPage'
import { TeamCalendarPage } from './pages/TeamCalendarPage'
import { PeriodClosuresPage } from './pages/PeriodClosuresPage'
import { SurchargeRulesPage } from './pages/SurchargeRulesPage'
import { ChecklistsPage } from './pages/ChecklistsPage'
import { ReportsPage } from './pages/ReportsPage'
import { TeamsPage } from './pages/TeamsPage'
import { TenantsPage } from './pages/TenantsPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/passwort-zuruecksetzen" element={<ResetPasswordPage />} />
            <Route
              path="/mein-bereich"
              element={
                <ProtectedRoute area="self-service">
                  <SelfServicePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/mandanten"
              element={
                <ProtectedRoute area="super-admin">
                  <SuperAdminLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<TenantsPage />} />
            </Route>
            <Route
              path="/"
              element={
                <ProtectedRoute area="hr">
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<DashboardPage />} />
              <Route path="mitarbeiter" element={<EmployeesPage />} />
              <Route path="mitarbeiter-import" element={<EmployeeBulkImportPage />} />
              <Route path="employees/:employeeId" element={<EmployeeDetailPage />} />
              <Route path="uebersicht" element={<AttendanceOverviewPage />} />
              <Route path="team-kalender" element={<TeamCalendarPage />} />
              <Route path="zu-klaeren" element={<OpenDaysPage />} />
              <Route path="monatsabschluss" element={<PeriodClosuresPage />} />
              <Route path="checklisten" element={<ChecklistsPage />} />
              <Route path="auswertungen" element={<ReportsPage />} />
              <Route path="standorte" element={<LocationsPage />} />
              <Route path="tablets" element={<DevicesPage />} />
              <Route path="feiertage" element={<HolidaysPage />} />
              <Route path="urlaubsantraege" element={<PendingAbsencesPage />} />
              <Route path="pausenregeln" element={<BreakRulesPage />} />
              <Route path="teams" element={<TeamsPage />} />
              <Route path="schichtvorlagen" element={<ShiftTemplatesPage />} />
              <Route path="schichtplan-kalender" element={<ShiftPlanCalendarPage />} />
              <Route path="einstellungen" element={<SettingsPage />} />
              <Route path="audit-log" element={<AuditLogPage />} />
              <Route path="lohn-export" element={<PayrollExportPage />} />
              <Route path="zuschlaege" element={<SurchargeRulesPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
