import { NavLink, Outlet } from 'react-router-dom'
import { Activity, Building2, LogOut } from 'lucide-react'
import { cn } from '../../lib/utils'
import { BrandLogo } from './BrandLogo'
import { useAuth } from '../../auth/AuthContext'
import { ChangePasswordButton } from '../account/ChangePasswordDialog'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100',
    isActive && 'bg-slate-900 text-white hover:bg-slate-900',
  )

export function SuperAdminLayout() {
  const { logout } = useAuth()

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-slate-200 bg-white p-4">
        <div className="mb-6 px-2">
          <BrandLogo showTenantLogo={false} />
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          <NavLink to="/mandanten" end className={linkClass}>
            <Building2 className="h-4 w-4" />
            Mandanten
          </NavLink>
          <NavLink to="/mandanten/server" className={linkClass}>
            <Activity className="h-4 w-4" />
            Server
          </NavLink>
        </nav>
        <ChangePasswordButton className="flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900" />
        <button
          type="button"
          onClick={logout}
          className="flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        >
          <LogOut className="h-4 w-4" />
          Abmelden
        </button>
      </aside>
      <main className="flex-1 bg-slate-50 p-6">
        <Outlet />
      </main>
    </div>
  )
}
