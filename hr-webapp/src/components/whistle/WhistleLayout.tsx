import { Link, Outlet } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { AppLayout } from '../layout/AppLayout'
import { BrandLogo } from '../layout/BrandLogo'
import { NotificationBell } from '../layout/NotificationBell'

/** Rahmen für „Hinweise“: Beauftragte mit Verwaltungsrolle arbeiten in der HR-Ansicht, Beauftragte ohne
 * Verwaltungsrolle (z. B. Mitarbeiter) in einem schlichten Rahmen mit Weg zurück nach „Mein Bereich“. */
export function WhistleLayout() {
  const { hasHrAccess, employeeId, logout } = useAuth()
  if (hasHrAccess) return <AppLayout />
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 md:px-6">
        <BrandLogo />
        <div className="flex items-center gap-3">
          {employeeId !== null && (
            <Link to="/mein-bereich" className="text-sm text-sky-700 hover:underline">
              Mein Bereich
            </Link>
          )}
          <NotificationBell align="right" />
          <button type="button" onClick={logout} className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-800">
            <LogOut className="h-4 w-4" />
            Abmelden
          </button>
        </div>
      </header>
      <main className="p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  )
}
