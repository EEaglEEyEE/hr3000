import type { ReactNode } from 'react'
import { useAuth } from '../../auth/AuthContext'
import { allows, type Access } from '../../lib/access'

/** Schützt eine Seite nach der Rechte-Tabelle (lib/access.ts) – dieselben Stufen wie Menü und Backend.
 * Wer die Adresse direkt aufruft, sieht einen Hinweis statt einer halb leeren Seite. */
export function RequireAccess({ access, children }: { access: Access; children: ReactNode }) {
  const { isAdmin, isFullHr, canPayroll } = useAuth()
  if (!allows(access, { isAdmin, isFullHr, canPayroll })) {
    return <p className="text-slate-500">Für diese Seite fehlt die Berechtigung.</p>
  }
  return <>{children}</>
}
