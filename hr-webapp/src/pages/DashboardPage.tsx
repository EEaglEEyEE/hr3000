import { Navigate } from 'react-router-dom'
import { useFeaturesQuery } from '../api/queries/workTimeModel'
import { useAuth } from '../auth/AuthContext'
import { Dashboard } from '../components/dashboard/Dashboard'
import { allowsPage } from '../lib/access'

export function DashboardPage() {
  const { isAdmin, isFullHr, canPayroll, perms } = useAuth()
  const flags = { isAdmin, isFullHr, canPayroll, perms }
  const features = useFeaturesQuery()
  // Eigene Rolle ohne Tagesgeschäft (z. B. „Lohnbüro (nur lesen)“): direkt zur Lohnbuchhaltung
  if (perms && !allowsPage('/', flags)) {
    if (features.isLoading) return <p className="text-slate-500">Lädt…</p>
    if (features.data?.payroll_accounting_enabled && allowsPage('/lohnbuchhaltung', flags)) {
      return <Navigate to="/lohnbuchhaltung" replace />
    }
    return <p className="text-slate-500">Ihrer Rolle ist noch kein Bereich freigegeben.</p>
  }
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Startseite</h1>
      <Dashboard />
    </div>
  )
}
