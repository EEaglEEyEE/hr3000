import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'

export function ProtectedRoute({
  children,
  area,
}: {
  children: ReactNode
  area: 'hr' | 'self-service' | 'super-admin'
}) {
  const { isAuthenticated, hasHrAccess, isSuperAdmin, employeeId } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  if (area === 'super-admin') {
    if (!isSuperAdmin) {
      return <Navigate to="/" replace />
    }
    return <>{children}</>
  }
  // Der Super-Admin ist keinem Mandanten zugeordnet – in den mandantenscoped
  // Bereichen (hr/self-service) gibt es für ihn nichts zu sehen.
  if (isSuperAdmin) {
    return <Navigate to="/mandanten" replace />
  }
  if (area === 'hr' && !hasHrAccess) {
    return <Navigate to="/mein-bereich" replace />
  }
  // Mitarbeiter mit HR-Rolle dürfen zusätzlich in ihren eigenen Bereich (eigene Monatsnachweise,
  // Dokumente, Saldo) – nur reine HR-Konten ohne Mitarbeiterdatensatz nicht.
  if (area === 'self-service' && hasHrAccess && employeeId === null) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}
