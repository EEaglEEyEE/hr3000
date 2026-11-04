import { Outlet } from 'react-router-dom'
import { Building2, LogOut } from 'lucide-react'
import { BrandLogo } from './BrandLogo'
import { useAuth } from '../../auth/AuthContext'
import { ChangePasswordButton } from '../account/ChangePasswordDialog'

export function SuperAdminLayout() {
  const { logout } = useAuth()

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-slate-200 bg-white p-4">
        <div className="mb-6 px-2">
          <BrandLogo showTenantLogo={false} />
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          <div className="flex items-center gap-2 rounded-md bg-slate-900 px-2 py-2 text-sm font-medium text-white">
            <Building2 className="h-4 w-4" />
            Mandanten
          </div>
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
