import { Dashboard } from '../components/dashboard/Dashboard'

export function DashboardPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Startseite</h1>
      <Dashboard />
    </div>
  )
}
