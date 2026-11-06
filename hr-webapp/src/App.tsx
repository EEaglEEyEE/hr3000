import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { AppLayout } from './components/layout/AppLayout'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { RequireAccess } from './components/layout/RequireAccess'
import { PAGE_ACCESS } from './lib/access'
import { SuperAdminLayout } from './components/layout/SuperAdminLayout'
import { AttendanceOverviewPage } from './pages/AttendanceOverviewPage'
import { EmployeeBulkImportPage } from './pages/EmployeeBulkImportPage'
import { EmployeeDetailPage } from './pages/EmployeeDetailPage'
import { DashboardPage } from './pages/DashboardPage'
import { EmployeesPage } from './pages/EmployeesPage'
import { LoginPage } from './pages/LoginPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { OpenDaysPage } from './pages/OpenDaysPage'
import { PayrollExportPage } from './pages/PayrollExportPage'
import { SelfServicePage } from './pages/SelfServicePage'
import { SettingsPage } from './pages/SettingsPage'
import { ShiftPlanCalendarPage } from './pages/ShiftPlanCalendarPage'
import { TeamCalendarPage } from './pages/TeamCalendarPage'
import { PeriodClosuresPage } from './pages/PeriodClosuresPage'
import { ChecklistsPage } from './pages/ChecklistsPage'
import { ReportsPage } from './pages/ReportsPage'
import { TenantsPage } from './pages/TenantsPage'
import { ServerMetricsPage } from './pages/ServerMetricsPage'

/** Frühere Menüpunkte, die jetzt Bereiche der Einstellungen sind (alte Links und Lesezeichen). */
const MOVED_TO_SETTINGS: Record<string, string> = {
  standorte: 'standorte',
  teams: 'teams',
  feiertage: 'feiertage',
  pausenregeln: 'pausen',
  schichtvorlagen: 'schichtplanung',
  tablets: 'tablets',
  zuschlaege: 'zuschlaege',
  lohnarten: 'lohnarten',
  'audit-log': 'audit-log',
}

/** Seite mit den Rechten aus lib/access.ts schützen. */
function guarded(path: string, page: ReactElement): ReactElement {
  const access = PAGE_ACCESS[path]
  return access ? <RequireAccess access={access}>{page}</RequireAccess> : page
}

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
              <Route path="server" element={<ServerMetricsPage />} />
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
              <Route path="mitarbeiter-import" element={guarded('/mitarbeiter-import', <EmployeeBulkImportPage />)} />
              <Route path="employees/:employeeId" element={<EmployeeDetailPage />} />
              <Route path="uebersicht" element={<AttendanceOverviewPage />} />
              <Route path="team-kalender" element={<TeamCalendarPage />} />
              <Route path="zu-klaeren/:reiter?" element={<OpenDaysPage />} />
              {/* Früher eigener Menüpunkt, jetzt Reiter im Posteingang „Zu klären“ */}
              <Route path="urlaubsantraege" element={<Navigate to="/zu-klaeren/urlaubsantraege" replace />} />
              <Route path="schichtplan-kalender" element={guarded('/schichtplan-kalender', <ShiftPlanCalendarPage />)} />
              <Route path="monatsabschluss" element={guarded('/monatsabschluss', <PeriodClosuresPage />)} />
              <Route path="auswertungen" element={guarded('/auswertungen', <ReportsPage />)} />
              <Route path="lohn-export" element={guarded('/lohn-export', <PayrollExportPage />)} />
              <Route path="checklisten" element={guarded('/checklisten', <ChecklistsPage />)} />
              <Route path="einstellungen/:seite?" element={guarded('/einstellungen', <SettingsPage />)} />
              {/* Frühere eigene Seiten, jetzt Bereiche der Einstellungen */}
              {Object.entries(MOVED_TO_SETTINGS).map(([path, section]) => (
                <Route key={path} path={path} element={<Navigate to={`/einstellungen/${section}`} replace />} />
              ))}
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
